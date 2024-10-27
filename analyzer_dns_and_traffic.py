import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple


class DNSLogAnalyzer:
    def __init__(self, start_date: str, end_date: str):
        """初始化 DNS 日誌分析器"""
        self.elastic_base_path = Path("elastic_query_results")
        self.dns_base_path = Path("dns_query_results")
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")

    def get_date_range(self) -> List[str]:
        """生成指定日期範圍內的所有日期"""
        date_list = []
        current_date = self.start_date
        while current_date <= self.end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            if (
                (self.elastic_base_path / date_str).exists() and
                (self.dns_base_path / date_str).exists()
            ):
                date_list.append(date_str)
            current_date += timedelta(days=1)
        return date_list

    def load_json_file(self, file_path: Path) -> Dict:
        """載入並解析JSON文件"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {str(e)}")
            return None

    def get_available_ips(self, date: str) -> List[str]:
        """獲取指定日期下所有可用的IP"""
        elastic_ips = set(f.stem for f in (self.elastic_base_path / date).glob("*.json"))
        dns_files = (self.dns_base_path / date).glob("*.json")
        dns_ips = set(f.stem for f in dns_files if not f.stem.startswith("dns_queries_"))
        return sorted(elastic_ips & dns_ips)

    def process_elastic_data(self, elastic_data: Dict) -> Dict[str, int]:
        """處理彈性搜索數據"""
        ip_counts = defaultdict(int)
        if elastic_data and 'data' in elastic_data:
            for ip, count in elastic_data['data'].items():
                ip_counts[ip] = count
        return ip_counts

    def process_dns_data(self, dns_data: Dict) -> Dict[str, Set[Tuple[str, str]]]:
        """處理DNS查詢數據，返回所有DNS答案的映射"""
        dns_mappings = defaultdict(set)  # 改用set避免重複
        if dns_data and 'records' in dns_data:
            for record in dns_data['records']:
                question_name = record['question_name'].rstrip('.')
                if question_name.endswith('.in-addr.arpa'):
                    continue
                dst_ip = record['dst_ip']
                # 將問題名稱和所有回答IP配對儲存
                for answer_ip in record['answer_ips']:
                    dns_mappings[dst_ip].add((question_name, answer_ip))
        return dns_mappings

    def analyze_device(self, date: str, ip: str) -> List[Dict]:
        """分析單一設備的數據，包含所有DNS答案"""
        results = []
        elastic_data = self.load_json_file(self.elastic_base_path / date / f"{ip}.json")
        dns_data = self.load_json_file(self.dns_base_path / date / f"{ip}.json")

        if not elastic_data or not dns_data:
            return []

        ip_counts = self.process_elastic_data(elastic_data)
        dns_mappings = self.process_dns_data(dns_data)
        processed_ips = set()

        # 處理所有DNS解析結果
        for question_name, answer_ip in dns_mappings[ip]:
            # 獲取訪問次數，如果沒有訪問記錄則為0
            access_count = ip_counts.get(answer_ip, 0)
            results.append({
                'Date': date,
                'Device_IP': ip,
                'DNS_Questions_Name': question_name,
                'DNS_Answer_A': answer_ip,
                'Access_IP_Count': access_count
            })
            processed_ips.add(answer_ip)

        # 處理直接IP訪問（沒有DNS查詢的IP）
        for target_ip, count in ip_counts.items():
            if target_ip not in processed_ips:
                dns_name = "IP direct access"
                if target_ip == "8.8.8.8":
                    dns_name = "DNS Server"
                results.append({
                    'Date': date,
                    'Device_IP': ip,
                    'DNS_Questions_Name': dns_name,
                    'DNS_Answer_A': target_ip,
                    'Access_IP_Count': count
                })

        return results

    def analyze_all_devices(self) -> List[Dict]:
        """分析所有設備在指定時間範圍內的數據"""
        dates = self.get_date_range()

        total_files = sum(len(self.get_available_ips(date)) for date in dates)
        processed_files = 0

        print(f"Analyzing data from {self.start_date.date()} to {self.end_date.date()}")
        print(f"Found {len(dates)} dates and {total_files} files to process")

        # 使用字典來合併相同項目的訪問次數
        consolidated = defaultdict(int)
        dns_names = {}  # 儲存每個IP對應的DNS name

        for date in dates:
            for ip in self.get_available_ips(date):
                processed_files += 1
                print(f"Processing {date}/{ip} ({processed_files}/{total_files})")

                results = self.analyze_device(date, ip)
                for result in results:
                    key = (result['Device_IP'], result['DNS_Answer_A'])
                    consolidated[key] += result['Access_IP_Count']
                    # 保存DNS name的對應關係
                    if result['DNS_Questions_Name'] != "IP direct access":
                        dns_names[key] = result['DNS_Questions_Name']

        # 轉換回列表格式
        final_results = []
        for key, count in consolidated.items():
            device_ip, answer_ip = key
            dns_name = dns_names.get(key, "IP direct access")
            if answer_ip == "8.8.8.8":
                dns_name = "DNS Server"

            final_results.append({
                'Device_IP': device_ip,
                'DNS_Questions_Name': dns_name,
                'DNS_Answer_A': answer_ip,
                'Access_IP_Count': count
            })

        # 按訪問次數降序、DNS名稱和答案IP升序排序
        return sorted(
            final_results,
            key=lambda x: (-x['Access_IP_Count'], x['DNS_Questions_Name'], x['DNS_Answer_A'])
        )

    def write_csv(self, results: List[Dict], filename: str) -> None:
        """寫入CSV文件"""
        if not results:
            print("No results to write")
            return

        fieldnames = ['Device_IP', 'DNS_Questions_Name', 'DNS_Answer_A', 'Access_IP_Count']
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print(f"Results written to {filename}")
        print(f"Total records: {len(results)}")


def main():
    # 指定分析的時間範圍
    start_date = "2024-10-13"
    end_date = "2024-10-19"

    # 建立分析器實例
    analyzer = DNSLogAnalyzer(start_date, end_date)

    # 執行分析
    results = analyzer.analyze_all_devices()

    # 生成包含時間範圍的輸出文件名
    output_file = f"dns_analysis_{start_date}_to_{end_date}.csv"

    # 寫入結果
    analyzer.write_csv(results, output_file)

    print("\nAnalysis complete!")


if __name__ == "__main__":
    main()
