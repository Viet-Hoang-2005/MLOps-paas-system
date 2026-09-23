# extract_data.py: Script trích xuất dữ liệu cho tập Train, Test và Data Drift từ bộ CICIDS2017
import os

import pandas as pd


def prep_paas_dynamic_data(file_path, output_dir):
    print(f"Đang nạp dữ liệu gốc từ: {file_path}")
    df = pd.read_csv(file_path)
    print(f"Tổng số dòng ban đầu: {len(df)}")

    if "Attack Type" in df.columns:
        df.rename(columns={"Attack Type": "Label"}, inplace=True)

    # 1. KHAI BÁO ÁNH XẠ 5 NHÃN
    label_mapping = {
        "Normal Traffic": "BENIGN",
        "DDoS": "DDoS",
        "Port Scanning": "PortScan",
        "Brute Force": "BruteForce",
        "Web Attacks": "WebAttacks",
    }

    df_filtered = df[df["Label"].isin(label_mapping.keys())].copy()
    df_filtered["Label"] = df_filtered["Label"].map(label_mapping)

    # 2. LẤY MẪU ĐỘNG (DYNAMIC SAMPLING) CHỐNG LỖI MẤT CÂN BẰNG
    sampled_dfs = []
    test_dfs = []

    for label in label_mapping.values():
        df_label = df_filtered[df_filtered["Label"] == label]
        available_count = len(df_label)

        test_count = min(1000, int(available_count * 0.2))
        max_train_available = available_count - test_count

        if label == "BENIGN":
            target_count = min(100000, max_train_available)
        else:
            target_count = min(50000, max_train_available)

        print(
            f"[+] Nhãn {label:<10} | Có sẵn: {available_count:<8} -> Sẽ trích xuất: {target_count}"
        )

        df_sampled = df_label.sample(n=target_count, random_state=42)
        sampled_dfs.append(df_sampled)

        df_remaining = df_label.drop(df_sampled.index)
        df_test = df_remaining.sample(n=test_count, random_state=42)
        test_dfs.append(df_test)

    # 3. GỘP TẬP REFERENCE TỔNG (CHỨA CẢ 5 NHÃN)
    final_df = pd.concat(sampled_dfs, ignore_index=True)
    final_df = final_df.sample(frac=1, random_state=42).reset_index(drop=True)
    out_ref = os.path.join(output_dir, "reference_data.csv")
    final_df.to_csv(out_ref, index=False)
    print(f"\n✅ Đã lưu Reference Data tổng ({len(final_df)} dòng) tại: {out_ref}")

    # 4. GỘP TẬP TEST TỔNG (Phần dữ liệu dư ra để API test)
    test_final_df = pd.concat(test_dfs, ignore_index=True)
    test_final_df = test_final_df.sample(frac=1, random_state=42).reset_index(drop=True)
    out_test = os.path.join(output_dir, "test_data.csv")
    test_final_df.to_csv(out_test, index=False)
    print(f"✅ Đã lưu Test Data dư thừa ({len(test_final_df)} dòng) tại: {out_test}")

    # 5. XUẤT KỊCH BẢN V1 (2 NHÃN: BENIGN + DDoS)
    labels_2 = ["BENIGN", "DDoS"]
    df_2_classes = final_df[final_df["Label"].isin(labels_2)].copy()
    out_2_classes = os.path.join(output_dir, "train_2_classes.csv")
    df_2_classes.to_csv(out_2_classes, index=False)
    print(f"✅ Đã lưu Kịch bản 2 Nhãn ({len(df_2_classes)} dòng) tại: {out_2_classes}")

    # 6. XUẤT KỊCH BẢN V2 (3 NHÃN: BENIGN + DDoS + PortScan)
    labels_3 = ["BENIGN", "DDoS", "PortScan"]
    df_3_classes = final_df[final_df["Label"].isin(labels_3)].copy()
    out_3_classes = os.path.join(output_dir, "train_3_classes.csv")
    df_3_classes.to_csv(out_3_classes, index=False)
    print(f"✅ Đã lưu Kịch bản 3 Nhãn ({len(df_3_classes)} dòng) tại: {out_3_classes}")

    # 7. XUẤT KỊCH BẢN V3 (4 NHÃN: BENIGN + DDoS + PortScan + BruteForce)
    labels_4 = ["BENIGN", "DDoS", "PortScan", "BruteForce"]
    df_4_classes = final_df[final_df["Label"].isin(labels_4)].copy()
    out_4_classes = os.path.join(output_dir, "train_4_classes.csv")
    df_4_classes.to_csv(out_4_classes, index=False)
    print(f"✅ Đã lưu Kịch bản 4 Nhãn ({len(df_4_classes)} dòng) tại: {out_4_classes}")

    # 8. XUẤT KỊCH BẢN V4 (5 NHÃN: BENIGN + DDoS + PortScan + BruteForce + WebAttacks)
    out_5_classes = os.path.join(output_dir, "train_5_classes.csv")
    final_df.to_csv(out_5_classes, index=False)
    print(f"✅ Đã lưu Kịch bản 5 Nhãn ({len(final_df)} dòng) tại: {out_5_classes}")

    # 9. XUẤT FILE CHỈ CHỨA PORTSCAN
    df_portscan = final_df[final_df["Label"] == "PortScan"].copy()
    out_portscan = os.path.join(output_dir, "drift_portscan.csv")
    df_portscan.to_csv(out_portscan, index=False)
    print(
        f"🔥 Đã lưu Kịch bản Drift - PortScan ({len(df_portscan)} dòng) tại: {out_portscan}"
    )

    # 10. XUẤT FILE CHỈ CHỨA BRUTEFORCE
    df_bruteforce = final_df[final_df["Label"] == "BruteForce"].copy()
    out_bruteforce = os.path.join(output_dir, "drift_bruteforce.csv")
    df_bruteforce.to_csv(out_bruteforce, index=False)
    print(
        f"🔥 Đã lưu Kịch bản Drift - BruteForce ({len(df_bruteforce)} dòng) tại: {out_bruteforce}"
    )

    # 11. XUẤT FILE CHỈ CHỨA WEB ATTACKS
    df_webattacks = final_df[final_df["Label"] == "WebAttacks"].copy()
    out_webattacks = os.path.join(output_dir, "drift_webattacks.csv")
    df_webattacks.to_csv(out_webattacks, index=False)
    print(
        f"🔥 Đã lưu Kịch bản Drift - WebAttacks ({len(df_webattacks)} dòng) tại: {out_webattacks}"
    )


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)
INPUT_CSV = os.path.join(DATA_DIR, "cicids2017_cleaned.csv")

prep_paas_dynamic_data(INPUT_CSV, DATA_DIR)
