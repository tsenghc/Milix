import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import urllib3
from requests.auth import HTTPBasicAuth

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DateRange:
    """處理日期範圍的類別"""
    def __init__(self, start_date: str, end_date: str):
        """處理日期範圍的類別"""
        self.start = datetime.strptime(start_date, "%Y-%m-%d")
        self.end = datetime.strptime(end_date, "%Y-%m-%d")

    def get_dates(self) -> List[str]:
        """獲取日期範圍內的所有日期"""
        dates = []
        current = self.start
        while current <= self.end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return dates

    def get_date_range_for_query(self, date: str) -> tuple:
        """獲取單一日期的查詢時間範圍"""
        start_time = f"{date}T00:00:00Z"
        end_time = f"{date}T23:59:59Z"
        return start_time, end_time


class ElasticsearchQueryClient:    
    """Elasticsearch 查詢客戶端"""
    def __init__(self, host: str, username: str, password: str):
        self.host = host
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {"Content-Type": "application/json"}

    def read_ip_list(self, file_path: str) -> List[str]:
        """讀取 IP 列表"""
        try:
            with open(file_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"讀取 IP 列表失敗: {str(e)}")
            raise

    def build_query(self, ip: str, start_time: str, end_time: str) -> Dict:
        """建立 Elasticsearch 查詢"""
        return {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"DstIP.keyword": ip}},
                        {
                            "range": {
                                "Timestamp": {
                                    "gte": start_time,
                                    "lte": end_time
                                }
                            }
                        }
                    ]
                }
            },
            "_source": [
                "Timestamp",
                "DNS.Question.Name",
                "DNS.Answer.A",
                "DstIP",
                "SrcIP",
                "Protocol"
            ],
            "sort": [
                {"Timestamp": {"order": "asc"}}
            ],
            "size": 10000
        }

    def process_dns_data(self, source: Dict) -> Dict:
        """處理 DNS 資料"""
        dns_data = source.get('DNS', {})
        question_name = ""
        answer_ips = []

        if 'Question' in dns_data and dns_data['Question']:
            question_name = dns_data['Question'][0].get('Name', '')

        if 'Answer' in dns_data and dns_data['Answer']:
            answer_ips = [answer['A'] for answer in dns_data['Answer'] if 'A' in answer]

        return {
            'timestamp': source['Timestamp'],
            'dst_ip': source['DstIP'],
            'question_name': question_name,
            'answer_ips': answer_ips,
            'src_ip': source['SrcIP'],
            'protocol': source['Protocol']
        }

    def check_existing_file(self, file_path: str) -> bool:
        """檢查文件是否存在且有效"""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'records' in data:  # 檢查文件格式是否正確
                        return True
            except (json.JSONDecodeError, KeyError):
                print(f"檔案 {file_path} 存在但格式無效")
                return False
        return False

    def query_dns_records(self, ip: str, start_time: str, end_time: str) -> Optional[Dict]:
        """查詢 DNS 記錄"""
        query = self.build_query(ip, start_time, end_time)

        try:
            response = requests.post(
                f"{self.host}/pi-dnsmonster*/_search",
                auth=self.auth,
                headers=self.headers,
                data=json.dumps(query),
                verify=False,
                timeout=30
            )

            if response.status_code == 200:
                json_response = response.json()
                results = []

                if 'hits' in json_response and 'hits' in json_response['hits']:
                    for hit in json_response['hits']['hits']:
                        if 'DNS' in hit['_source']:
                            results.append(self.process_dns_data(hit['_source']))

                return {'records': results}
            else:
                print(f"查詢 IP {ip} 失敗，狀態碼：{response.status_code}")
                print(f"回應內容：{response.text}")
                return None

        except Exception as e:
            print(f"查詢 IP {ip} 時發生錯誤：{str(e)}")
            return None

    def collect_data(self, start_date: str, end_date: str, ip_list_file: str, output_dir: str):
        """收集 DNS 查詢資料"""
        ip_list = self.read_ip_list(ip_list_file)
        date_range = DateRange(start_date, end_date)
        dates = date_range.get_dates()

        print(f"開始處理 {len(dates)} 天的資料")
        new_queries_performed = False

        for date in dates:
            start_time, end_time = date_range.get_date_range_for_query(date)
            date_dir = os.path.join(output_dir, date)
            os.makedirs(date_dir, exist_ok=True)

            for ip in ip_list:
                file_path = os.path.join(date_dir, f"{ip}.json")

                # 檢查是否已有有效的查詢結果
                if self.check_existing_file(file_path):
                    print(f"找到 {date} 日期 IP {ip} 的現有查詢結果，跳過查詢")
                    continue

                print(f"查詢 IP: {ip}, 日期: {date}")
                result = self.query_dns_records(ip, start_time, end_time)

                if result:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    print(f"已儲存到 {file_path}")
                    new_queries_performed = True

        if not new_queries_performed:
            print("所有查詢結果已存在，未執行新的查詢")
        else:
            print("已完成所有新查詢的處理")


def main():
    # 固定配置
    ELASTICSEARCH_HOST = "https://127.0.0.1:9200"
    USERNAME = "elastic"
    PASSWORD = "password"
    IP_LIST_FILE = "ip_list.txt"
    OUTPUT_DIR = "dns_query_results"
    START_DATE = "2024-10-13"
    END_DATE = "2024-10-19"

    try:
        client = ElasticsearchQueryClient(
            ELASTICSEARCH_HOST,
            USERNAME,
            PASSWORD
        )

        print("開始收集資料...")
        client.collect_data(
            START_DATE,
            END_DATE,
            IP_LIST_FILE,
            OUTPUT_DIR
        )

        print("查詢完成")

    except Exception as e:
        print(f"執行過程中發生錯誤: {str(e)}")


if __name__ == "__main__":
    main()
