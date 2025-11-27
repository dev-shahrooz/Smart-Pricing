# Smart Pricing Engine

## Overview
This project is a Django-based Smart Pricing Engine designed for manufacturing companies that produce embedded furniture electronics, such as in-wall chargers and audio modules. It streamlines bill-of-material uploads, organizes components, and applies pricing logic tailored to these specialized products.

## Tech Stack
- **Backend:** Django
- **Frontend:** Django templates with pure HTML, CSS, and vanilla JavaScript
- **Data Input:** CSV-based BOM upload

## Application Structure
- `pricing/domain_models.py`: Core domain entities used across the pricing workflow.
- `pricing/bom_loader.py`: CSV-driven bill-of-material ingestion utilities.
- `pricing/pricing_engine.py`: Pricing logic orchestrator that works off the loaded BOM and domain models.
- `pricing/state.py`: Shared state management helpers for the pricing engine.
- Templates under `templates/pricing/`: HTML views for interacting with the pricing engine through the Django UI.

## How to Run
1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Apply migrations: `python manage.py migrate`
4. Start the development server: `python manage.py runserver`

## Future Work
Phase 2 will introduce machine learning modules under `pricing/ml/` to enhance pricing accuracy and automation.

## Machine Learning Features
- Demand elasticity modeling from sales CSV.
- Optimal price recommendation based on profit maximization.
- Optional USD rate forecasting.
- Ensemble pricing suggestions.

## ML Data Formats
- Sales CSV: `month,product_code,price,units_sold`
- USD CSV: `date,usd_rate`

## ML Commands
- `python manage.py train_elasticity <sales_csv_path> <cost_per_unit>`
- `python manage.py train_usd_forecast <usd_csv_path>`

## AI Insights Page
The AI Insights page surfaces the trained models' recommendations, including elasticity estimates, price suggestions, and USD rate projections. Use it to explore forecast results and adjust pricing decisions directly from the UI.
