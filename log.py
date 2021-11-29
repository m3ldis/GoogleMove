import logging

log_level = 'INFO'
logging.basicConfig(filename='out.log', style='{', format='{asctime}s {levelname}:{name}: {message}')
logger = logging.getLogger("main")
logger.setLevel(log_level)
