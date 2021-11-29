import traceback
from log import logger
from drive_service import DriveClient
import json
import os
import variables as vvars
import zendesk_service as zd
from googleapiclient.errors import HttpError

'''
This file contains all custom logic for migrating all folders and files from shared folder to Shared Drive.
'''

dc = DriveClient()
IDCSV = 'ids.csv'
OLDCASE = vvars.F_Redacted
NEWCASE = vvars.F_TEAM_DRIVE_Redacted
STRUCTURE = ['redacted list of desired subfolder structure for new shared drive folders']
ZD_MOVED_COMMENT = 'During a Google Drive migration to the shared drive, some files were moved...'
FOLDER_MAP = {'redacted old folder': 'redacted new folder', 'redacted1': 'redacted2', 'redacted2': 'redacted2'}


def cache_container_folders():
    if os.stat('folder_cache.json').st_size > 2:
        return
    ticket_l0 = 'redacted'
    tickets_l1 = dc.list_files(ticket_l0).get('files')  # 2000-level containers
    cache = {}
    for item in tickets_l1:
        n, i = item.get('name'), item.get('id')
        cache[n] = {'id': i, 'folders': {}}
        tmp_tickets_l2 = dc.list_files(i).get('files')
        cache[n]['folders'] = {item_l2.get('name'): item_l2.get('id') for item_l2 in tmp_tickets_l2}
    with open('folder_cache.json', 'w', encoding='utf-8') as outfile:
        json.dump(obj=cache, fp=outfile)


def get_ticket_destination(ticket_num_str: str):
    """New folders are placed in top-level numbered folders in the team drive; find which one a new item will go into"""
    cache_container_folders()
    with open('folder_cache.json', 'r', encoding='utf-8') as infile:
        cache = json.load(infile)
    ticket_int = int(ticket_num_str)
    for name_1st_lvl, val_1st_lvl in cache.items():
        folder_boundaries = name_1st_lvl.split(' ')[1].split('-')
        if int(folder_boundaries[0]) <= ticket_int <= int(folder_boundaries[1]):
            first_lvl_folder = cache[name_1st_lvl]
            for name_2nd_level, id_2nd_level in first_lvl_folder.get('folders').items():
                folder_boundaries = name_2nd_level.split('-')
                if int(folder_boundaries[0]) <= ticket_int <= int(folder_boundaries[1]):
                    logger.debug(f'Folder destination for ticket {ticket_num_str}: "{name_2nd_level}" {id_2nd_level}')
                    return id_2nd_level
                else:
                    continue
        else:
            continue


class Folder:

    def __init__(self, folder_name: str, folder_id: str, drive_client: DriveClient):
        self.name = folder_name
        self.id = folder_id
        self.dc = drive_client
        self.dest_folder_id: [str, None] = None


class NewTicketFolder(Folder):

    def __init__(self, folder_name: str, ntf_id: str, drive_client: DriveClient, preexisting: bool = False):
        super().__init__(folder_name, ntf_id, drive_client)
        if preexisting:
            self.structure = drive_client.get_structure(folder_id=ntf_id)
        else:
            logger.info(f'Creating structure under new ticket folder {ntf_id}...')
            self.structure = {subfolder_name: self.dc.create_folder(name=subfolder_name, parent=ntf_id)
                              for subfolder_name in STRUCTURE}


class OriginalTicketFolder(Folder):

    def __init__(self, folder_name: str, folder_id: str, drive_client: DriveClient, new_folder_id: str = None):
        """:param new_folder_id: for when we already created a folder in the shared drive (i.e. this is a retry)"""
        super().__init__(folder_name, folder_id, drive_client)
        self.SKIP = False
        try:
            self.ticket_number = self.name.split('#')[1].split()[0]
        except IndexError:
            logger.warning(f'The title of folder {folder_id} is malformed and I can\'t determine where it goes. '
                           'Please migrate this folder manually.')
            with open('err.txt', 'a') as errfile:
                traceback.print_exc(file=errfile)
                errfile.write('='*40)
            self.SKIP = True
            return
        self.division_folder_id = get_ticket_destination(self.ticket_number)  # "1-50", etc
        self.contains_utf_files = False
        if new_folder_id:
            self.dest_folder_id = new_folder_id
            self.new_folder = NewTicketFolder(folder_name=folder_name, ntf_id=self.dest_folder_id,
                                              drive_client=self.dc, preexisting=True)
            logger.info(f'Retrying migration for {folder_name}')
        else:
            logger.info(f'Creating new folder "{folder_name}"...')
            self.dest_folder_id = self.dc.create_folder(name=folder_name, parent=self.division_folder_id)
            self.new_folder = NewTicketFolder(folder_name=folder_name, ntf_id=self.dest_folder_id,
                                              drive_client=self.dc)

    def migrate_single_file(self, file_id: str):
        self.dc.move_files_location(old_folder=self.id, new_folder=self.new_folder.id,
                                    file_list=[file_id])


class Subfolder(Folder):

    def __init__(self, folder_name: str, folder_id: str, parent: Folder, drive_client: DriveClient):
        """
        :param folder_name: name of this folder
        :param folder_id: id of this folder
        :param parent: parent Folder instance
        """
        super().__init__(folder_name, folder_id, drive_client)
        self.files = []
        self.dest_folder_id = None
        self.parent = parent

    def get_queue(self):
        """Get queue of folders and files to re-create/move"""
        if not self.dest_folder_id:
            raise Exception(f'Cannot get queue for a folder that has not been copied yet ({self.name})')
        folder_queue: list[Subfolder] = []
        files_queue: list[dict] = []
        is_empty = True
        self.files = dc.list_files(self.id).get('files')
        if self.files:
            is_empty = False
            for subfile_object in self.files:
                if subfile_object.get('mimeType') == 'application/vnd.google-apps.folder':
                    folder_queue.append(Subfolder(folder_name=subfile_object.get('name'),
                                                  folder_id=subfile_object.get('id'),
                                                  parent=self,
                                                  drive_client=self.dc))
                else:
                    files_queue.append(subfile_object.get('id'))
        return is_empty, folder_queue, files_queue

    def migrate(self):
        if not self.dest_folder_id:
            raise Exception(f'Cannot move files from a folder that has not been copied yet ({self.name})')
        is_empty, folder_queue, files_queue = self.get_queue()

        if is_empty:
            return
        self.dc.move_files_location(old_folder=self.id, new_folder=self.dest_folder_id, file_list=files_queue)
        files_queue.clear()

        while folder_queue:
            current_subfolder = folder_queue.pop(0)
            current_subfolder.dest_folder_id = self.dc.create_folder(name=current_subfolder.name,
                                                                     parent=current_subfolder.parent.dest_folder_id)
            tmp_is_empty, tmp_folder_queue, tmp_files_queue = current_subfolder.get_queue()
            if tmp_is_empty:
                continue

            if tmp_files_queue:
                self.dc.move_files_location(old_folder=current_subfolder.id,
                                            new_folder=current_subfolder.dest_folder_id,
                                            file_list=tmp_files_queue)
            if tmp_folder_queue:
                folder_queue.extend(tmp_folder_queue)

    def delete(self):
        pass


class StructureSubfolder(Subfolder):

    def __init__(self, folder_name: str, folder_id: str, parent_object: OriginalTicketFolder,
                 drive_client: DriveClient):
        """This is a direct subfolder of a Ticket folder. It won't ever be folders within those folders.
        :param folder_name: name of this folder, needed for mapping this folder to a new one in shared drive
        :param folder_id: id of this folder
        :param parent_object: OriginalTicketFolder instance with some info we'll need about the folder
        """
        super().__init__(folder_name=folder_name, folder_id=folder_id, parent=parent_object, drive_client=drive_client)
        self.dest_folder_id = parent_object.new_folder.structure.get(
            FOLDER_MAP.get(self.name, 'redacted'))
        self.folder_map = {}
        self.parent = parent_object


def migrate_one(folder_object: dict, retry: bool = False, new_folder_id: str = None):
    if retry and new_folder_id:
        otf = OriginalTicketFolder(folder_name=folder_object.get('name'), folder_id=folder_object.get('id'),
                                   drive_client=dc, new_folder_id=new_folder_id)
    else:
        otf = OriginalTicketFolder(folder_name=folder_object.get('name'), folder_id=folder_object.get('id'),
                                   drive_client=dc)
        if otf.SKIP:
            logger.warning(f'Migration for {folder_object.get("name")} was skipped!')
            return
        with open(IDCSV, 'a', encoding='utf-8') as f:
            f.write(f'{otf.id},{otf.new_folder.id},"{otf.name}"\n')

    logger.info(f'Starting migration for "{otf.name}" ({otf.id})')
    otf_files = dc.list_files(otf.id).get('files')
    for subitem in otf_files:
        if subitem.get('mimeType') != 'application/vnd.google-apps.folder':
            otf.migrate_single_file(subitem.get('id'))
            continue

        subf = StructureSubfolder(folder_name=subitem.get('name'), folder_id=subitem.get('id'),
                                  parent_object=otf, drive_client=dc)
        subf.migrate()
        subf.delete()

    zd.update_custom_field(otf.ticket_number, otf.new_folder.id, field_name='Google Drive ID')
    utf = dc.list_files(folder_id=otf.new_folder.structure.get('redacted')).get('files')
    if len(utf) > 0:
        logger.info(f'Commenting on ticket {otf.ticket_number}')
        zd.internal_comment_on_ticket(otf.ticket_number, ZD_MOVED_COMMENT, vvars.zendesk_user_id)

    with open('done', 'a', encoding='utf-8') as f2:
        f2.write(f'{folder_object.get("id")}\n')

    try:
        dc.delete_folder(folder_object.get('id'))
    except HttpError as httpe:
        err_reason = httpe.error_details[0].get('reason')
        if err_reason == 'insufficientFilePermissions':
            logger.info(f'Could not delete {folder_object.get("id")} due to insufficient permissions.')


def migrate_all(folder_id: str = OLDCASE):
    response = dc.list_files(folder_id)
    while response:
        file_list = response.get('files')
        print(len(file_list))
        with open('done', 'r', encoding='utf-8') as inf:
            done_files = inf.read().splitlines()
        for fo in file_list:
            if fo.get('id') in done_files:
                continue
            migrate_one(folder_object=fo)
        next_page_token = response.get('nextPageToken', None)
        if next_page_token:
            response = dc.list_files(folder_id, next_page_token=next_page_token)
        else:
            logger.info("No more files to migrate!")
            response = None


migrate_all()
