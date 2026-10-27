def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert "database" in data["components"]
    assert data["components"]["database"]["status"] == "connected"
    assert "latency_ms" in data["components"]["database"]
    assert "version" in data
    assert "timestamp" in data


def test_prometheus_metrics_endpoint(client, auth_headers):
    # Perform a request to generate metrics
    client.get("/api/v1/projects", headers=auth_headers)

    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    assert "taskflow_http_requests_total" in content
    assert "taskflow_http_request_duration_seconds" in content
    assert "process_cpu_seconds_total" in content or "python_info" in content
