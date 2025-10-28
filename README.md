🧠 Smokeball Power BI Connector

Automated API integration between Smokeball and Power BI using Azure Functions, Power Query, and Dataflows

📘 Overview

This project provides a secure, automated integration layer between the Smokeball API and Power BI Service.
It enables organizations using Smokeball (case management software) to:

Automatically extract key operational data (contacts, matters, billing, etc.)

Refresh Power BI datasets and dataflows on a scheduled basis

Maintain up-to-date analytics without manual token refresh or CSV exports

Built using:

🪣 Azure Functions (Python) — token management, API orchestration, retry logic

☁️ Azure Storage (Blob) — token and lock state for concurrency-safe refreshes

💡 Power Query / Dataflows — transformation and semantic modeling in Power BI
