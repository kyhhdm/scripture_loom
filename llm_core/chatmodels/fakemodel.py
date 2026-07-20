from .basechain import BaseChain
from .basemodel import BaseModel, logger
from langchain_community.llms import FakeListLLM

class Fake2Chat(BaseChain, BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.create_llm(chat_model=FakeListLLM,
                        responses=["这是一个测试用的模型回复",
                                   "ahhhhhh"])

    def chat(self, msg, *arg, **kwargs):
        self.llm.responses = [f"Human:{msg} \nAI: 这是一个测试模型"]
        logger.info(f'testmodel msg_len: {len(msg)}')
        return self.llm.invoke(msg), True

    def new_chat(self, *args, **kwargs):
        return  'test', False