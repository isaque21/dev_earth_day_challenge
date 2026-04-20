
# 🦜 Arara Watch: Global Disaster Monitor & Ecological Intelligence

![Arara Watch Banner](app/bg_site.png)

**Arara Watch** is an AI-powered environmental monitoring platform built for the **Earth Day Weekend Challenge**. It bridges the gap between raw climate data and actionable human insight by transforming satellite feeds into a structured "Threat Matrix" and providing deep ecological context for any location on Earth.

---

## 🌍 Overview

When extreme weather events occur, raw numbers aren't enough. **Arara Watch** acts as a Civil Defense Analyst, evaluating real-time data to alert users about:
- 🔥 Wildfires (NASA Satellite Data)
- 🌊 Floods & Landslides (Rainfall Analysis)
- 🌡️ Extreme Heat & Cold (Thermal Analysis)
- 🌿 Ecological Health (AI-Generated Biome Overview)

## 🚀 Architecture

The project follows a **100% Serverless** approach for maximum scalability and zero maintenance cost.

- **Frontend:** Vanilla JS/CSS/HTML hosted on **Amazon S3** and distributed via **Amazon CloudFront**.
- **Backend:** **AWS Lambda** (Python 3.12) triggered by **Amazon API Gateway**.
- **Security:** API Keys managed via **AWS Secrets Manager**.
- **Database/Cache:** **Amazon DynamoDB** with Global Secondary Index (GSI).
- **IA:** **Google Gemini 2.5 Flash** for cognitive data analysis.
- **Infrastructure:** Fully automated via **Terraform (IaC)**.

---

## 🧠 Key Feature: Proximity Caching

To prevent API rate limits and reduce latency, Arara Watch implements a **Proactive Proximity Cache**. 

Instead of querying the AI for every exact coordinate, the system normalizes locations to a ~1.1km radius. If a nearby location was analyzed in the last 30 minutes, the system serves the result instantly from **DynamoDB**, saving costs and tokens.

```python
# Caching logic snippet
cache_key = f"{round(lat, 2)},{round(lon, 2)}_en_v2"
````

-----

## 🛠️ Setup & Installation

### Prerequisites

  - AWS CLI configured
  - Terraform installed
  - Google Gemini API Key
  - OpenWeatherMap API Key
  - NASA FIRMS API Key

### Infrastructure Deployment (Terraform)

1.  Navigate to the `/terraform` directory.
2.  Initialize and apply:
    ```bash
    terraform init
    terraform apply -var="gemini_api_key=..." -var="openweathermap_api_key=..." -var="nasa_firms_api_key=..."
    ```

### Frontend Deployment

1.  Update `API_URL` in `script.js` with your API Gateway endpoint.
2.  Sync files to S3:
    ```bash
    aws s3 sync ./frontend s3://your-arara-watch-bucket
    ```

-----

## 🎨 UI/UX: Earth Theme

The interface uses **Glassmorphism** to create a modern, nature-connected feel.

  - **Green/Blue Palette:** Reflecting Earth's forests and oceans.
  - **Dynamic Threat Matrix:** Color-coded badges for LOW, MEDIUM, and HIGH risk levels.
  - **Responsive Design:** Optimized for both desktop monitoring and mobile field use.

-----

## 🛡️ License

This project is licensed under the MIT License.

## 👥 Acknowledgments

  - **Google Gemini** for the incredible reasoning capabilities.
  - **NASA FIRMS** for the real-time wildfire data.
  - **OpenWeather** for the global climate API.

-----

*Created for the Earth Day Weekend Challenge 2026.*

