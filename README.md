# Milix

## 專案簡介

隨著物聯網（IoT）設備的普及，安全性成為一大關注焦點。本專案旨在透過簡易的硬體與開源工具，提供一套有效的 IoT 安全防護方案，保護您的智慧家居免受各類網路威脅。

## 解決方案

本專案僅使用 **Arkime** 與  **DNS Monster** ，並搭配 **Raspberry Pi** 實作，專為 IoT 設備設計的安全防護系統。透過以下步驟，輕鬆建立一個穩固的 IoT 安全環境。

DNSMonster v1.0.0beta2 : [mosajjal/dnsmonster: Passive DNS Capture and Monitoring Toolkit (github.com)](https://github.com/mosajjal/dnsmonster)

Arkime v5.4: [arkime/arkime: Arkime is an open source, large scale, full packet capturing, indexing, and database system. (github.com)](https://github.com/arkime/arkime)

## 功能特點

* **Raspberry Pi 作為 AP** ：使用 Raspberry Pi 當作無線接入點，讓 IoT 設備連入受控網路。
* **長時間資料搜集** ：持續監控網路流量，建立全面的設備行為資料庫。
* **白名單設定** ：根據搜集到的資料，設定信任的設備與服務 IP 白名單。
* **反向告警機制** ：針對非白名單 IP 發出即時警報，確保及時應對潛在威脅。
* **效能優化** ：不分析封包內容，只監控連接行為，節省系統資源。
* **全面風險防護** ：除了手機與官方 IoT 雲端服務外，所有其他封包皆視為潛在風險，提升整體安全性。

## 安裝步驟

1. **編輯配置檔**
   打開 `milix.config` 檔案，根據您的網路環境與需求進行相應的配置調整。
2. **執行安裝腳本**
   在終端機中執行以下指令，開始安裝所需套件與設定：

   ```
   /bin/bash ./milix-install.sh
   ```
3. 執行重啟腳本(如果忘記他每日五點會自己重啟)
4. ```
   $HOME/milix_service_restart.sh
   ```
5. **啟動系統**
   安裝完成後，系統將自動啟動，開始進行資料搜集與風險監控。您可透過相關介面查看警報與日誌。

## 分析腳本

collector_dns_query: 收集期間的每日 DNS 紀錄

collector_traffic_log: 收集期間內的 arkime 流量紀錄

analyzer_traffic_trend: 分析 arkime 的流量趨勢

analyzer_dns_and_traffic: 分析 DNS 紀錄對應到的 IP 清單，並合併存取次數


## 架構圖

<p align="center">
  <img src="https://github.com/tsenghc/Milix/blob/main/image/milix_architecture.png" alt="Milix架構圖" width='50%' height='50%'/>
</p>

## 貢獻指南

歡迎所有對 IoT 安全有興趣的開發者與使用者，透過提交問題（Issue）或 Pull Request 的方式，共同完善本專案。

## 授權條款

本專案採用 [MIT 授權]()，歡迎自由使用與修改。
