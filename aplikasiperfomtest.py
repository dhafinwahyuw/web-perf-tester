import sys
import streamlit.runtime as st_runtime
from streamlit.web import cli as stcli

if not st_runtime.exists():
    sys.argv = ["streamlit", "run", sys.argv[0]]
    sys.exit(stcli.main())

import concurrent.futures
import statistics
import time
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Web Performance Tester",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        padding: 16px 20px;
        border-radius: 10px;
        color: white;
    }
    div[data-testid="stMetric"] label {
        color: rgba(255, 255, 255, 0.9) !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: white !important;
        font-weight: 700;
    }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: rgba(255, 255, 255, 0.85) !important;
    }
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .subtitle {
        color: #6b7280;
        margin-bottom: 20px;
    }
</style>
""",
    unsafe_allow_html=True,
)


def validate_url(url: str) -> bool:
    try:
        res = urlparse(url)
        return all([res.scheme in ("http", "https"), res.netloc])
    except Exception:
        return False


def send_single_request(url: str, timeout: int, req_index: int) -> dict:
    data = {
        "request_no": req_index,
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "status_code": None,
        "response_time_ms": None,
        "content_length_kb": None,
        "success": False,
        "error": None,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    try:
        t0 = time.perf_counter()
        res = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        elapsed = time.perf_counter() - t0

        data["status_code"] = res.status_code
        data["response_time_ms"] = round(elapsed * 1000, 2)
        data["content_length_kb"] = round(len(res.content) / 1024, 2)
        data["success"] = res.status_code < 400
    except requests.exceptions.Timeout:
        data["error"] = "Timeout"
    except requests.exceptions.ConnectionError:
        data["error"] = "Connection Error"
    except requests.exceptions.RequestException as e:
        data["error"] = str(e)[:60]

    return data


def classify_response_time(ms: float) -> str:
    if ms < 200:
        return "Sangat Cepat"
    elif ms < 500:
        return "Cepat"
    elif ms < 1000:
        return "Sedang"
    elif ms < 3000:
        return "Lambat"
    return "Sangat Lambat"


def get_grade(avg_ms: float) -> tuple[str, str]:
    if avg_ms < 200:
        return "A+", "#16a34a"
    elif avg_ms < 400:
        return "A", "#22c55e"
    elif avg_ms < 700:
        return "B", "#eab308"
    elif avg_ms < 1200:
        return "C", "#f97316"
    elif avg_ms < 2500:
        return "D", "#ef4444"
    return "F", "#991b1b"


with st.sidebar:
    st.header("Konfigurasi Pengujian")

    target_url = st.text_input(
        "Target URL",
        value="https://id.wikipedia.org",
    )

    num_requests = st.slider("Jumlah Requests", 5, 100, 15, step=5)
    timeout_sec = st.slider("Timeout (detik)", 5, 60, 15, step=5)
    delay_sec = st.slider("Delay per Request (detik)", 0.0, 3.0, 0.5, step=0.1)
    concurrent_workers = st.slider("Concurrent Workers", 1, 10, 1)

    st.markdown("---")
    st.subheader("Presets")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Wikipedia ID", use_container_width=True):
            st.session_state["preset_url"] = "https://id.wikipedia.org"
            st.rerun()
        if st.button("Google", use_container_width=True):
            st.session_state["preset_url"] = "https://www.google.com"
            st.rerun()
    with c2:
        if st.button("Wikipedia EN", use_container_width=True):
            st.session_state["preset_url"] = "https://en.wikipedia.org"
            st.rerun()
        if st.button("GitHub", use_container_width=True):
            st.session_state["preset_url"] = "https://github.com"
            st.rerun()

    if "preset_url" in st.session_state:
        target_url = st.session_state.pop("preset_url")


st.markdown(
    '<div class="main-title">Web Performance Tester</div>', unsafe_allow_html=True
)
st.markdown(
    '<div class="subtitle">Benchmarking response time website dengan HTTP requests bertahap</div>',
    unsafe_allow_html=True,
)

col_u1, col_u2, col_u3 = st.columns(3)
col_u1.write(f"**Target:** `{target_url}`")
col_u2.write(f"**Sample:** `{num_requests}` reqs | **Timeout:** `{timeout_sec}s`")
col_u3.write(f"**Delay:** `{delay_sec}s` | **Workers:** `{concurrent_workers}`")

if st.button("Mulai Performance Test", type="primary", use_container_width=True):
    if not validate_url(target_url):
        st.error("Format URL tidak valid. Gunakan http:// atau https://")
        st.stop()

    progress = st.progress(0)
    status = st.empty()
    t_start = time.perf_counter()

    if concurrent_workers > 1:
        results = []
        batches = [
            list(range(i, min(i + concurrent_workers, num_requests)))
            for i in range(0, num_requests, concurrent_workers)
        ]
        done = 0
        for batch in batches:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(batch)
            ) as executor:
                futures = [
                    executor.submit(
                        send_single_request, target_url, timeout_sec, idx + 1
                    )
                    for idx in batch
                ]
                for fut in concurrent.futures.as_completed(futures):
                    results.append(fut.result())
                    done += 1
                    progress.progress(done / num_requests)
                    status.text(f"Mengirim request {done}/{num_requests}...")
            if delay_sec > 0:
                time.sleep(delay_sec)
        results.sort(key=lambda x: x["request_no"])
    else:
        results = []
        for i in range(num_requests):
            status.text(f"Mengirim request {i + 1}/{num_requests}...")
            r = send_single_request(target_url, timeout_sec, i + 1)
            results.append(r)
            progress.progress((i + 1) / num_requests)
            if delay_sec > 0 and i < num_requests - 1:
                time.sleep(delay_sec)

    total_duration = time.perf_counter() - t_start
    progress.empty()
    status.empty()

    df = pd.DataFrame(results)
    st.session_state["results"] = results
    st.session_state["df"] = df
    st.session_state["total_duration"] = total_duration
    st.session_state["target_url"] = target_url
    st.session_state["num_requests"] = num_requests


if "results" in st.session_state:
    df = st.session_state["df"]
    target_url = st.session_state["target_url"]
    total_duration = st.session_state["total_duration"]
    num_req = st.session_state["num_requests"]

    success_df = df[df["success"] == True]
    fail_df = df[df["success"] == False]
    success_rate = (len(success_df) / num_req) * 100

    if success_rate == 0:
        st.error(f"Semua request ke {target_url} gagal.")
        st.stop()

    times = success_df["response_time_ms"].tolist()
    avg_t = statistics.mean(times)
    med_t = statistics.median(times)
    min_t = min(times)
    max_t = max(times)
    std_t = statistics.stdev(times) if len(times) > 1 else 0.0

    sorted_t = sorted(times)
    p90 = sorted_t[max(int(len(sorted_t) * 0.90) - 1, 0)]
    p95 = sorted_t[max(int(len(sorted_t) * 0.95) - 1, 0)]

    grade, grade_col = get_grade(avg_t)

    st.markdown("---")
    st.markdown(
        f"""
        <div style="text-align: center; margin: 10px 0 25px 0;">
            <div style="font-size: 3.5rem; font-weight: 800; color: {grade_col};">{grade}</div>
            <div style="color: #6b7280; font-size: 0.95rem;">Rating Performa: {classify_response_time(avg_t)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rata-rata", f"{avg_t:.1f} ms")
    m2.metric("Minimum", f"{min_t:.1f} ms")
    m3.metric("Maksimum", f"{max_t:.1f} ms")
    m4.metric("Median", f"{med_t:.1f} ms")

    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Std Deviasi", f"{std_t:.1f} ms")
    m6.metric("P90", f"{p90:.1f} ms")
    m7.metric("P95", f"{p95:.1f} ms")
    m8.metric("Success Rate", f"{success_rate:.1f}%")

    st.write(f"Total waktu uji: **{total_duration:.2f} detik**")

    st.subheader("Visualisasi")
    tab1, tab2, tab3 = st.tabs(["Line Chart", "Histogram", "Box Plot"])

    with tab1:
        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=success_df["request_no"],
                y=success_df["response_time_ms"],
                mode="lines+markers",
                name="Response Time",
                line=dict(color="#4f46e5", width=2),
            )
        )
        fig_line.add_hline(
            y=avg_t,
            line_dash="dash",
            line_color="#ef4444",
            annotation_text=f"Avg: {avg_t:.1f} ms",
        )
        fig_line.update_layout(
            xaxis_title="Request #",
            yaxis_title="Response Time (ms)",
            template="plotly_white",
            height=380,
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with tab2:
        fig_hist = px.histogram(
            success_df,
            x="response_time_ms",
            nbins=15,
            color_discrete_sequence=["#6366f1"],
            labels={"response_time_ms": "Response Time (ms)"},
        )
        fig_hist.update_layout(template="plotly_white", height=380)
        st.plotly_chart(fig_hist, use_container_width=True)

    with tab3:
        fig_box = px.box(
            success_df,
            y="response_time_ms",
            color_discrete_sequence=["#8b5cf6"],
            labels={"response_time_ms": "Response Time (ms)"},
        )
        fig_box.update_layout(template="plotly_white", height=380)
        st.plotly_chart(fig_box, use_container_width=True)

    st.subheader("Detail Log Request")
    display_df = df[
        [
            "request_no",
            "timestamp",
            "status_code",
            "response_time_ms",
            "content_length_kb",
            "success",
            "error",
        ]
    ].copy()

    display_df.columns = [
        "No",
        "Waktu",
        "Status",
        "Response Time (ms)",
        "Size (KB)",
        "Sukses",
        "Error",
    ]

    st.dataframe(
        display_df.style.map(
            lambda v: (
                "background-color: #dcfce7"
                if v is True
                else ("background-color: #fee2e2" if v is False else "")
            ),
            subset=["Sukses"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Data CSV",
        data=csv_bytes,
        file_name=f"benchmark_{datetime.now():%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
    )
