# ---------------------------------------------------------
# 
# ---------------------------------------------------------
"""定义chat model chain function"""
import re
import sys
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_classic.chains import ConversationChain
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from typing import Union
from collections import defaultdict

class BaseChain(object):
    max_token = 0
    batch_size_limit = 0
    batch_chat_limit = 0
    input_token_num = 0

    def __init__(self, **kwargs) -> None:
        self.init_args(**kwargs)

    def init_args(self, **kwargs):
        [setattr(self, k, v) for k,v in kwargs.items() if not hasattr(self, k)]

    def create_llm(self, chat_model, **kwargs):
        self.llm = chat_model(**kwargs)

    def create_history_store(self, sql_model, **kwargs):
        self.history_store = sql_model(**kwargs)

    def create_conver_memory(self, memory_model, **kwargs):
        self.memory = memory_model(**kwargs)

    def create_conver_chain(self, **kwargs):
        """  be deprecated in LangChain 0.2.7 and will be removed in 1.0 """
        self.conv_chain = ConversationChain(**kwargs)

    # todo 
    def create_chain(self, **kwargs):
        """  update by next version"""
        self.conv_chain = RunnableWithMessageHistory()

    def humanMessage(self, msg):
        return HumanMessage(msg)
    
    def systemMessage(self, msg):
        return SystemMessage(msg)
    
    def aiMessage(self, msg):
        return AIMessage(msg)

    def get_prompt_cost(self, tokennums:int):
        return self.input_price * tokennums

    def get_num_tokens(self, msg:str, *args, **kwargs):
        return self.conv_chain.llm.get_num_tokens(msg)
    
    def check_token_num(self, msg:str):
        return self.get_num_tokens(msg) < self.max_token
    
    def check_batch_size(self, batch_list):
        return  sys.getsizeof(batch_list) < self.batch_size_limit and len(batch_list) < self.batch_chat_limit
    
    def batch_llm(self, msgs: list, *args, **kwargs):
        result = self.llm.batch(msgs)
        return result
    
    async def abatch_llm(self, msgs: list, *args, **kwargs):
        async_object = self.llm.abatch(msgs)
        result = []
        async for s in async_object:
            result.append(s)
        return result

    def format_Message(self, msg: Union[HumanMessage, AIMessage, SystemMessage]):
        return {'role':{AIMessage:'assistant',
                        HumanMessage:'user',
                        SystemMessage: 'system'}.get(type(msg)),
                'content': msg.content}
    
    def detect_repetition_efficient(self, text, min_repeat_length=2, min_repeat_count=3):
        """
        高效检测文本中的重复模式
        :param text: 输入文本
        :param min_repeat_length: 最小重复单元长度(字符数)
        :param min_repeat_count: 最小重复次数阈值
        :return: 检测结果字典
        """
        # 1. 检测整行重复（针对结构化数据）
        if '\n' in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 10:  # 只在有多行时检测
                line_counts = defaultdict(int)
                for line in lines:
                    line_counts[line] += 1
                
                # 检查是否有行重复次数超过阈值
                max_line_repeat = max(line_counts.values(), default=0)
                if max_line_repeat >= min_repeat_count:
                    repeated_lines = [line for line, count in line_counts.items() if count >= min_repeat_count]
                    return {
                        "repetition_type": "line_repetition",
                        "max_repeat_count": max_line_repeat,
                        "repeated_lines": repeated_lines,
                        "repeated_text": f"检测到{max_line_repeat}次行重复"
                    }
        
        # 2. 高效局部重复检测（只检查文本尾部）
        n = len(text)
        if n < min_repeat_length * min_repeat_count:
            return {"repetition_type": False}
        
        # 只检查最后一部分文本（避免处理整个长文本）
        check_length = min(1000, n)  # 最多检查1000个字符
        tail_text = text[-check_length:]
        
        # 使用正则表达式检测重复模式
        results = []
        
        # 检测连续相同字符的重复
        char_pattern = r'((.)\2{' + str(min_repeat_count - 1) + r',})'
        for match in re.finditer(char_pattern, tail_text):
            pattern = match.group(2)
            count = len(match.group(1))
            results.append((pattern, count))
        
        # 检测更长的重复模式（最多检测5个字符的单元）
        for pattern_length in range(min_repeat_length, 6):
            pattern_regex = r'((.{' + str(pattern_length) + r'})\2{' + str(min_repeat_count - 1) + r',})'
            for match in re.finditer(pattern_regex, tail_text):
                pattern = match.group(2)
                count = len(match.group(1)) // len(pattern)
                results.append((pattern, count))
        
        if results:
            # 取重复次数最多的模式
            top_pattern, max_count = max(results, key=lambda x: x[1])
            return {
                "repetition_type": "pattern_repetition",
                "max_repeat_count": max_count,
                "repeated_pattern": top_pattern,
                "repeated_text": f"检测到模式 '{top_pattern}' 重复 {max_count} 次"
            }
        
        return {"repetition_type": False}


   








