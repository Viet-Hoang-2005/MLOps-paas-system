# predict.py: Kiểm thử độ chính xác của mô hình trả về từ API
import os
import pandas as pd
import requests
import time
from dotenv import load_dotenv

# 1. CẤU HÌNH ĐƯỜNG DẪN VÀ ENDPOINT
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TEST_CSV_PATH = os.path.join(ROOT_DIR, 'data', 'test_data.csv')

# Tự động load biến môi trường từ file .env
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# Đọc API_URL và đảm bảo nó trỏ đúng vào endpoint /predict
API_URL = os.environ.get("API_URL", "http://localhost:5000").rstrip('/')
API_KEY = os.environ.get("API_KEY")

def api_test_continuous(samples_per_class=1):
    print(f"STARTING CONTINUOUS API INFERENCE TEST...")
    
    # 2. NẠP DỮ LIỆU TEST
    if not os.path.exists(TEST_CSV_PATH):
        print(f"Could not find file {TEST_CSV_PATH}. Please check the path!")
        return

    df = pd.read_csv(TEST_CSV_PATH)
    print(f"[+] Loaded test dataset with {len(df)} rows.\n")

    try:
        # 3. VÒNG LẶP VÔ HẠN
        while True:
            # Bốc ngẫu nhiên số lượ ng đều nhau cho mỗi nhãn ở mỗi chu kỳ
            sample_df = df.groupby('Label').sample(n=samples_per_class, random_state=None)
            
            # Xáo trộn dữ liệu đã bốc mẫu 
            sample_df = sample_df.sample(frac=1, random_state=None).reset_index(drop=True)

            # Duyệt qua toàn bộ dữ liệu đã bốc mẫu và gửi từng dòng lên API để kiểm tra dự đoán
            for index, row in sample_df.iterrows():
                print("-" * 50)

                # Tách nhãn thực tế và đặc trưng từ dòng dữ liệu
                actual_label = row['Label']
                features = row.drop('Label').to_dict()

                # payload JSON gửi features lên API
                payload = {
                    "features": features
                }

                print(f"Sending network packet (Actual label: {actual_label})...")
                
                try:
                    # Đo thời gian từ lúc gửi request đến khi nhận được phản hồi để tính độ trễ (latency)
                    start_time = time.time()
                    
                    headers = {}
                    if API_KEY:
                        headers["X-API-Key"] = API_KEY
                        
                    response = requests.post(API_URL, json=payload, headers=headers)
                    end_time = time.time()
                    
                    latency = round((end_time - start_time) * 1000, 2)

                    # Xử lý phản hồi từ API
                    if response.status_code == 200:
                        # Nhận kết quả dự đoán từ API
                        result = response.json() 
                        predicted_label = result.get('prediction')
                        # Tự động ánh xạ (Map) nếu model trả về 0/1 thay vì chữ
                        label_mapping = {0: "BENIGN", 1: "DDoS"}
                        if predicted_label in label_mapping:
                            predicted_label = label_mapping[predicted_label]
                        elif str(predicted_label) in ["0", "1"]:
                            predicted_label = label_mapping[int(predicted_label)]
                        
                        # So sánh dự đoán với nhãn thực tế để đánh giá đúng/sai
                        status_icon = "CORRECT" if predicted_label == actual_label else "WRONG"
                        
                        print(f"{status_icon} | Predicted: {predicted_label} | Latency: {latency}ms")
                        print(f"Probability details: {result.get('probabilities')}")
                    else:
                        print(f"API Error (Status {response.status_code}): {response.text}")

                except requests.exceptions.ConnectionError:
                    print("Connection Error: API is not running!")
                    return
                    
                time.sleep(2) # Chờ 2s giữa các lần bắn request

    except KeyboardInterrupt:
        print("\nEND OF API TEST THREAD!")

if __name__ == "__main__":
    api_test_continuous(samples_per_class=1)