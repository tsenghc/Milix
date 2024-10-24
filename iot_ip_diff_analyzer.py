import requests
import json
from requests.auth import HTTPBasicAuth
import urllib3
from datetime import datetime, timedelta
import os
from typing import List, Optional, Generator, Dict, Set
import sys

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
        while current_dt < end_dt:
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
                f"{self.host}/_sql?format=txt",
                auth=self.auth,
                headers=self.headers,
                data=json.dumps(query),
                verify=False
            )
            
            if response.status_code == 200:
                return response.text.strip() if response.text.strip() else None
            else:
                print(f"查詢 IP {ip} 失敗，狀態碼：{response.status_code}")
                print(f"回應內容：{response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"查詢 IP {ip} 時發生錯誤：{e}")
            return None

    def parse_query_result(self, result_text: str) -> Dict[str, int]:
        """Parse the query result text and extract destination IPs with their counts."""
        if not result_text:
            return {}
            
        ip_counts = {}
        lines = result_text.strip().split('\n')[2:]  # Skip header lines
        
        for line in lines:
            parts = [part.strip() for part in line.split('|')]
            if len(parts) >= 2:
                ip = parts[0]
                count = int(parts[1])
                ip_counts[ip] = count
                
        return ip_counts

    def compare_days(self, prev_result: Dict[str, int], curr_result: Dict[str, int]) -> Dict[str, dict]:
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
        """Save query results for a specific day."""
        daily_dir = os.path.join(output_dir, date_str)
        os.makedirs(daily_dir, exist_ok=True)
        
        # Process and save each IP's results
        for ip, result in results.items():
            if result:
                filename = os.path.join(daily_dir, f"query_result_{ip}.txt")
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"Query results for IP: {ip}\n")
                    f.write(f"Date: {date_str}\n")
                    f.write("=" * 50 + "\n")
                    f.write(result)
                
                # Store parsed results for comparison
                if date_str not in self.daily_ip_data:
                    self.daily_ip_data[date_str] = {}
                self.daily_ip_data[date_str][ip] = self.parse_query_result(result)

    def generate_comparison_report(self, output_dir: str = "query_results"):
        """Generate and save the IP comparison report."""
        report_dir = os.path.join(output_dir, "comparison_reports")
        os.makedirs(report_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report_file = os.path.join(report_dir, f"ip_comparison_report_{timestamp}.txt")
        dates = sorted(self.daily_ip_data.keys())
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("IP 連線變化分析報告\n")
            f.write("=" * 50 + "\n\n")
            
            for i in range(len(dates) - 1):
                date1, date2 = dates[i], dates[i + 1]
                f.write(f"日期區間: {date1} → {date2}\n")
                f.write("-" * 50 + "\n\n")
                
                # Compare each source IP's results
                for source_ip in self.daily_ip_data[date1].keys():
                    prev_results = self.daily_ip_data[date1].get(source_ip, {})
                    curr_results = self.daily_ip_data[date2].get(source_ip, {})
                    
                    comparison = self.compare_days(prev_results, curr_results)
                    
                    f.write(f"Source IP: {source_ip}\n")
                    f.write("  新增的目標 IP:\n")
                    if comparison["added"]:
                        for ip, count in sorted(comparison["added"].items()):
                            f.write(f"    + {ip} (連線次數: {count})\n")
                    else:
                        f.write("    (無新增)\n")
                    
                    f.write("\n  移除的目標 IP:\n")
                    if comparison["removed"]:
                        for ip, count in sorted(comparison["removed"].items()):
                            f.write(f"    - {ip} (原連線次數: {count})\n")
                    else:
                        f.write("    (無移除)\n")
                    
                    f.write("\n  保持連線的目標 IP:\n")
                    if comparison["maintained"]:
                        for ip, (prev_count, curr_count) in sorted(comparison["maintained"].items()):
                            change = curr_count - prev_count
                            change_str = f"{'↑' if change > 0 else '↓' if change < 0 else '='}{abs(change)}"
                            f.write(f"    = {ip} ({prev_count} → {curr_count}, {change_str})\n")
                    else:
                        f.write("    (無維持的連線)\n")
                    
                    f.write("\n" + "-" * 30 + "\n\n")
                
                f.write("=" * 50 + "\n\n")
        
        print(f"比較報告已儲存到: {report_file}")
        return report_file

def main():
    # 配置
    ELASTICSEARCH_HOST = "https://x.x.x.x:9200"
    USERNAME = ""
    PASSWORD = ""
    IP_LIST_FILE = "ip_list.txt"
    OUTPUT_DIR = "elastic_query_results"
    
    # 查詢時間範圍
    START_DATE = "2024-10-10"
    END_DATE = "2024-10-15"
    
    # 初始化客戶端
    client = ElasticsearchQueryClient(ELASTICSEARCH_HOST, USERNAME, PASSWORD)
    
    try:
        # 讀取 IP 列表
        ip_list = client.read_ip_list(IP_LIST_FILE)
        print(f"已讀取 {len(ip_list)} 個 IP 地址")
        
        # 為每一天進行查詢
        for start_time, end_time in client.generate_date_ranges(START_DATE, END_DATE):
            date_str = start_time[:10]
            print(f"\n處理日期: {date_str}")
            
            # 對每個 IP 進行查詢
            daily_results = {}
            for ip in ip_list:
                print(f"正在查詢 IP: {ip}")
                result = client.query_single_ip(ip, start_time, end_time)
                if result:
                    daily_results[ip] = result
            
            # 儲存當天的結果
            client.save_daily_results(daily_results, date_str, OUTPUT_DIR)
        
        # 生成比較報告
        report_file = client.generate_comparison_report(OUTPUT_DIR)
        print("\n所有查詢和比較分析完成")
        
    except FileNotFoundError:
        print(f"找不到 IP 列表文件：{IP_LIST_FILE}")
        return
    except Exception as e:
        print(f"執行過程中發生錯誤：{e}")
        print(f"錯誤詳情: {str(e)}")
        return

if __name__ == "__main__":
    main()
