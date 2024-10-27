import csv
import json
import os
from datetime import datetime
from typing import Dict


class ElasticTrafficAnalyzer:
    def __init__(self, input_dir: str = "elastic_query_results"):
        """Initialize the analyzer with the input directory containing collected data"""
        self.input_dir = input_dir
        self.daily_ip_data = {}
        self.load_collected_data()

    def load_collected_data(self) -> None:
        """Load all collected JSON data from the input directory"""
        for date_dir in os.listdir(self.input_dir):
            if os.path.isdir(os.path.join(self.input_dir, date_dir)):
                self.daily_ip_data[date_dir] = {}
                date_path = os.path.join(self.input_dir, date_dir)

                for ip_file in os.listdir(date_path):
                    if ip_file.endswith('.json'):
                        with open(os.path.join(date_path, ip_file), 'r', encoding='utf-8') as f:
                            try:
                                data = json.load(f)
                                ip = data['metadata']['source_ip']
                                self.daily_ip_data[date_dir][ip] = data['data']
                            except json.JSONDecodeError:
                                print(f"Warning: Could not parse {ip_file}")
                            except KeyError:
                                print(
                                    f"Warning: Invalid data format in {ip_file}")

    def compare_days(self, prev_result: Dict[str, int],
                     curr_result: Dict[str, int]) -> Dict[str, dict]:
        """Compare IP addresses between two consecutive days"""
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

    def generate_csv_report(self, output_dir: str = "analysis_results") -> str:
        """Generate and save the IP comparison report in CSV format"""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_report_file = os.path.join(
            output_dir, f"ip_traffic_analysis_{timestamp}.csv")

        fieldnames = [
            "比較日期區間",
            "來源IP",
            "目標IP",
            "IP狀態",
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

            for i in range(len(dates) - 1):
                date1, date2 = dates[i], dates[i + 1]
                date_range = f"{date1} to {date2}"

                for source_ip in self.daily_ip_data[date1].keys():
                    prev_results = self.daily_ip_data[date1].get(source_ip, {})
                    curr_results = self.daily_ip_data[date2].get(source_ip, {})

                    comparison = self.compare_days(prev_results, curr_results)

                    # Write new IPs
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

                    # Write removed IPs
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

                    # Write maintained IPs
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

        print(f"分析報告已儲存到: {csv_report_file}")
        return csv_report_file


def main():
    # 建立分析器實例
    analyzer = ElasticTrafficAnalyzer()

    try:
        # 生成 CSV 報告
        csv_report_file = analyzer.generate_csv_report()
        print("\n分析完成！")
        print(f"報告檔案: {csv_report_file}")

    except Exception as e:
        print(f"分析過程中發生錯誤: {str(e)}")
        return


if __name__ == "__main__":
    main()
