# ---------------------------------------------------------
# 
# ---------------------------------------------------------
"""定义chat model function"""
import logging
logger = logging.getLogger(__name__)

class BaseModel(object):
    """Base Model for Chat Models."""
    def __init__(self, **kwargs):
        """Init method."""
        self.temperature = 0.5
    
    def warming_up(self):
        self.temperature = (lambda x: x + 0.051 if x < 0.15 else x)(self.temperature)

    def new_chat(self, *args, **kwargs) -> [str, bool]:
        chatid = ''
        return chatid, True

    def chat(self, msg, *args, **kwargs) -> [str, bool]:
        return msg, True

    def close_chat(self, **kwargs):
        """close Chat method."""
        pass 

    def batch_chat(self, *args, **kwargs):
        return 
    
    def abatch_chat(self, *args, **kwargs):
        return 

    def clean_cache(self, *args, **kwargs):
        return 
    
    def llm_chat(self, msg, user_msg, save_memory=True, **kwargs) -> str:
        return 