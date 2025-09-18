FROM python:3.11-slim
WORKDIR /app

# Install Streamlit + client libs
COPY ../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the UI entrypoint
COPY ../streamlit_app.py ./streamlit_app.py

EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "8501", "--server.headless", "true"]

