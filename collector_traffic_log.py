import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Generator, List, Optional

import requests
import urllib3
from requests.auth import HTTPBasicAuth

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ElasticsearchQueryClient:
    def __init__(self, host: str, username: str, password: str):
        """Initialize the Elasticsearch query client."""
        self.host = host
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {"Content-Type": "application/json"}
        self.daily_ip_data = {}

    def generate_date_ranges(self, start_date: str, end_date: str) -> Generator[tuple, None, None]:
        """Generate daily date ranges between start and end dates."""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        current_dt = start_dt
        while current_dt <= end_dt:
            next_dt = current_dt + timedelta(days=1)
            yield (
                current_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            current_dt = next_dt

    def read_ip_list(self, file_path: str) -> List[str]:
        """Read IP addresses from a file."""
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip()]

    def query_single_ip(self, ip: str, start_time: str, end_time: str) -> Optional[str]:
        """Query Elasticsearch for a single IP address in a specific time range."""
        query = {
            "query": f"""
                SELECT "destination.ip", COUNT(*) as count
                FROM "arkime_sessions3*"
                WHERE "source.ip" = '{ip}'
                AND "@timestamp" >= '{start_time}'
                AND "@timestamp" < '{end_time}'
                GROUP BY "destination.ip"
            """
        }

        try:
            response = requests.post(
                f"{self.host}/_sql?format=json",  # 改為請求 JSON 格式
                auth=self.auth,
                headers=self.headers,
                data=json.dumps(query),
                verify=False
            )

            if response.status_code == 200:
                return response.text if response.text.strip() else None
            else:
                print(f"查詢 IP {ip} 失敗，狀態碼：{response.status_code}")
                print(f"回應內容：{response.text}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"查詢 IP {ip} 時發生錯誤：{e}")
            return None

    def parse_query_result(self, result_text: str) -> Dict[str, int]:
        """Parse the JSON format query result and extract destination IPs with their counts.

        Args:
            result_text: JSON string containing the query results

        Returns:
            Dictionary with IP addresses as keys and their counts as values
        """
        if not result_text:
            return {}

        try:
            # 解析 JSON 字串
            result_json = json.loads(result_text)

            # 確認必要的資料結構存在
            if not all(key in result_json for key in ['columns', 'rows']):
                print("警告：回傳的 JSON 格式不正確")
                return {}

            # 找出 IP 和 count 的欄位索引
            ip_idx = -1
            count_idx = -1
            for i, column in enumerate(result_json['columns']):
                if column['name'] == 'destination.ip':
                    ip_idx = i
                elif column['name'] == 'count':
                    count_idx = i

            if ip_idx == -1 or count_idx == -1:
                print("警告：在回傳資料中找不到必要的欄位")
                return {}

            # 建立 IP 和計數的對應字典
            ip_counts = {}
            for row in result_json['rows']:
                ip = row[ip_idx]
                count = row[count_idx]
                ip_counts[ip] = count

            return ip_counts

        except json.JSONDecodeError:
            print("警告：無法解析 JSON 格式的回傳資料")
            return {}
        except Exception as e:
            print(f"警告：解析資料時發生錯誤: {str(e)}")
            return {}

    def compare_days(self, prev_result: Dict[str, int], 
                     curr_result: Dict[str, int]) -> Dict[str, dict]:
        """Compare IP addresses between two consecutive days."""
        prev_ips = set(prev_result.keys())
        curr_ips = set(curr_result.keys())

        added_ips = {ip: curr_result[ip] for ip in (curr_ips - prev_ips)}
        removed_ips = {ip: prev_result[ip] for ip in (prev_ips - curr_ips)}
        maintained_ips = {ip: (prev_result[ip], curr_result[ip])
                          for ip in (prev_ips & curr_ips)}

        return {
            "added": added_ips,
            "removed": removed_ips,
            "maintained": maintained_ips
        }

    def save_daily_results(self, results: dict, date_str: str, output_dir: str = "query_results"):
        """Save query results for a specific day in JSON format."""
        daily_dir = os.path.join(output_dir, date_str)
        os.makedirs(daily_dir, exist_ok=True)

        for ip, result in results.items():
            if result:
                try:
                    # 嘗試解析原始 JSON 字串以確保它是有效的
                    raw_json = json.loads(result)

                    # 準備儲存的資料結構
                    parsed_data = {
                        "metadata": {
                            "source_ip": ip,
                            "query_date": date_str,
                            "timestamp": datetime.now().isoformat()
                        },
                        "data": self.parse_query_result(result),
                        "raw_result": raw_json  # 儲存解析後的 JSON 物件
                    }

                    # 儲存為 JSON 檔案
                    filename = os.path.join(daily_dir, f"{ip}.json")
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(parsed_data, f, ensure_ascii=False, indent=2)

                except json.JSONDecodeError as e:
                    print(f"警告：IP {ip} 的查詢結果不是有效的 JSON 格式: {str(e)}")
                    continue
                except Exception as e:
                    print(f"警告：處理 IP {ip} 的查詢結果時發生錯誤: {str(e)}")
                    continue

    def generate_csv_report(self, output_dir: str = "query_results") -> str:
        """Generate and save the IP comparison report in CSV format.

        Args:
            output_dir: Directory to save the report

        Returns:
            str: Path to the generated CSV report file
        """
        import csv
        from datetime import datetime

        report_dir = os.path.join(output_dir, "comparison_reports")
        os.makedirs(report_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 設定 CSV 檔案路徑
        csv_report_file = os.path.join(
            report_dir, f"ip_traffic_report_{timestamp}.csv")

        # 定義 CSV 欄位
        fieldnames = [
            "比較日期區間",
            "來源IP",
            "目標IP",
            "IP狀態",  # 新增/移除/維持
            "前一天連線次數",
            "當天連線次數",
            "連線次數變化",
            "變化趨勢",
            "變化幅度"
        ]

        dates = sorted(self.daily_ip_data.keys())

        with open(csv_report_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # 比較每兩天的數據
            for i in range(len(dates) - 1):
                date1, date2 = dates[i], dates[i + 1]
                date_range = f"{date1} to {date2}"

                # 對每個來源 IP 進行分析
                for source_ip in self.daily_ip_data[date1].keys():
                    prev_results = self.daily_ip_data[date1].get(source_ip, {})
                    curr_results = self.daily_ip_data[date2].get(source_ip, {})

                    comparison = self.compare_days(prev_results, curr_results)

                    # 處理新增的 IP
                    for ip, count in comparison["added"].items():
                        writer.writerow({
                            "比較日期區間": date_range,
                            "來源IP": source_ip,
                            "目標IP": ip,
                            "IP狀態": "新增",
                            "前一天連線次數": 0,
                            "當天連線次數": count,
                            "連線次數變化": count,
                            "變化趨勢": "新增",
                            "變化幅度": count
                        })

                    # 處理移除的 IP
                    for ip, count in comparison["removed"].items():
                        writer.writerow({
                            "比較日期區間": date_range,
                            "來源IP": source_ip,
                            "目標IP": ip,
                            "IP狀態": "移除",
                            "前一天連線次數": count,
                            "當天連線次數": 0,
                            "連線次數變化": -count,
                            "變化趨勢": "移除",
                            "變化幅度": count
                        })

                    # 處理維持連線的 IP
                    for ip, (prev_count, curr_count) in comparison["maintained"].items():
                        change = curr_count - prev_count
                        trend = "增加" if change > 0 else "減少" if change < 0 else "不變"

                        writer.writerow({
                            "比較日期區間": date_range,
                            "來源IP": source_ip,
                            "目標IP": ip,
                            "IP狀態": "維持",
                            "前一天連線次數": prev_count,
                            "當天連線次數": curr_count,
                            "連線次數變化": change,
                            "變化趨勢": trend,
                            "變化幅度": abs(change)
                        })

        print(f"CSV 報告已儲存到: {csv_report_file}")
        return csv_report_file

    def check_existing_results(self, date_str: str, ip: str,
                               output_dir: str = "query_results") -> bool:
        """
        檢查特定日期和IP的查詢結果是否已存在

        Args:
            date_str: 日期字符串 (YYYY-MM-DD)
            ip: IP地址
            output_dir: 輸出目錄

        Returns:
            bool: 如果結果已存在返回True，否則返回False
        """
        file_path = os.path.join(output_dir, date_str, f"{ip}.json")
        if os.path.exists(file_path):
            try:
                # 檢查文件是否可以正常讀取且包含有效數據
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 檢查文件內容是否完整
                    if all(key in data for key in ['metadata', 'data']):
                        # 將已存在的數據加載到內存中
                        if date_str not in self.daily_ip_data:
                            self.daily_ip_data[date_str] = {}
                        self.daily_ip_data[date_str][ip] = data['data']
                        print(f"已找到 {date_str} 日期 IP {ip} 的現有查詢結果")
                        return True
            except (json.JSONDecodeError, KeyError):
                print(f"警告：{date_str} 日期 IP {ip} 的現有查詢結果無效，將重新查詢")
                return False
        return False
    
    def collect_traffic_data(self, start_date: str, end_date: str,
                             ip_list_file: str, output_dir: str):
        """Collect and process traffic data."""
        try:
            # 讀取 IP 列表
            ip_list = self.read_ip_list(ip_list_file)
            print(f"已讀取 {len(ip_list)} 個 IP 地址")

            # 為每一天進行查詢
            for start_time, end_time in self.generate_date_ranges(start_date, end_date):
                date_str = start_time[:10]
                print(f"\n處理日期: {date_str}")

                # 確保輸出目錄存在
                daily_dir = os.path.join(output_dir, date_str)
                os.makedirs(daily_dir, exist_ok=True)

                # 對每個 IP 進行查詢
                daily_results = {}
                for ip in ip_list:
                    # 檢查是否已有查詢結果
                    if not self.check_existing_results(date_str, ip, output_dir):
                        print(f"正在查詢 IP: {ip}")
                        result = self.query_single_ip(ip, start_time, end_time)
                        if result:
                            daily_results[ip] = result

                # 儲存查詢結果
                if daily_results:
                    self.save_daily_results(
                        daily_results, date_str, output_dir)

            print("\n資料收集完成")

        except FileNotFoundError:
            print(f"找不到 IP 列表文件：{ip_list_file}")
            raise
        except Exception as e:
            print(f"執行過程中發生錯誤：{e}")
            print(f"錯誤詳情: {str(e)}")
            raise


def main():
    # 固定配置
    ELASTICSEARCH_HOST = "https://127.0.0.1:9200"
    USERNAME = "elastic"
    PASSWORD = "password"
    IP_LIST_FILE = "ip_list.txt"
    OUTPUT_DIR = "elastic_query_results"
    START_DATE = "2024-10-13"
    END_DATE = "2024-10-19"

    try:
        client = ElasticsearchQueryClient(
            ELASTICSEARCH_HOST, USERNAME, PASSWORD)
        client.collect_traffic_data(
            START_DATE, END_DATE, IP_LIST_FILE, OUTPUT_DIR)
        print("收集完成！")
    except Exception as e:
        print(f"執行過程中發生錯誤: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
