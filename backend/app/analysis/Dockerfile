FROM python:3.13-slim
ENV MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN pip install --no-cache-dir "pandas>=2.2,<4" "numpy<3" "matplotlib<4" "seaborn<1" "openpyxl>=3.1" "xlrd>=2.0.1"
COPY table.py worker.py /opt/analysis/
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["timeout", "-s", "KILL", "35", "python", "-B", "/opt/analysis/worker.py"]
