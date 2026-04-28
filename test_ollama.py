import ollama
import time

def test_local_api():
    print("🚀 Bắt đầu gọi Local API (gemma4:e4b)...")
    print("-" * 50)
    
    # 1. Chuẩn bị câu hỏi (Prompt)
    messages = [
        {
            'role': 'system',
            'content': 'You are a Senior Python Developer. Answer clearly and concisely.'
        },
        {
            'role': 'user',
            'content': 'Write a very short Python function to calculate the Fibonacci sequence. Explain it in 1 sentence.'
        }
    ]

    # 2. Gọi API với chế độ Stream (nhả từng chữ)
    start_time = time.time()
    
    try:
        stream = ollama.chat(
            model='gemma4:e4b',
            messages=messages,
            stream=True # Bật tính năng giống ChatGPT
        )

        print("🤖 AI Trả lời:\n")
        for chunk in stream:
            # In ra từng token ngay khi nó được sinh ra
            print(chunk['message']['content'], end='', flush=True)
            
    except Exception as e:
        print(f"\n❌ Lỗi kết nối API: {e}")
        print("💡 Gợi ý: Hãy chắc chắn Ollama app đang được mở trên máy Mac của bạn.")
        
    end_time = time.time()
    print("\n" + "-" * 50)
    print(f"⏱️ Thời gian phản hồi: {round(end_time - start_time, 2)} giây")

if __name__ == "__main__":
    test_local_api()