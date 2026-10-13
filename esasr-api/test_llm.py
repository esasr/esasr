import os
import sys

# Add current directory to path so services can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.llm_service import analyze_search_query

def run_test():
    query = "近三年多模态大模型在医学影像诊断中的应用，需要开源代码和顶会论文"
    print("Testing query:", query)
    result = analyze_search_query(query)
    print("Result:", result)

if __name__ == "__main__":
    run_test()
