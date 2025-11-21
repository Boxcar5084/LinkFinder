# LinkFinder Quick Start Guide

Assuming your environment is set up and dependencies are installed.

## 1. Start the Backend Server

Open a terminal and run:

```bash
source venv/bin/activate
python main.py
```
*Leave this terminal open.*

## 2. Start the User Interface

Open a **second** terminal and run:

```bash
source venv/bin/activate
streamlit run streamlit_ui.py
```

This will open the interface in your browser (usually `http://localhost:8501`).

## 3. Run a Trace

1. Go to the **"New Trace"** tab.
2. Paste starting addresses in **List A**.
3. Paste target addresses in **List B**.
4. Click **"Start Trace"**.
5. Monitor progress in the **"Active Sessions"** tab.

## 4. Resume Interrupted Trace

If a trace stops or you restart the app:
1. Go to the **"Checkpoints"** tab.
2. Click **"Resume Latest"**.

