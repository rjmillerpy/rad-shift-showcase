"""Tests for app/metrics/service.py."""

import pytest
from prometheus_client.parser import text_string_to_metric_families

from app.metrics.service import LATENCY_BUCKETS, RequestMetrics

from .conftest import sample_value


def _render(metrics: RequestMetrics) -> str:
    return metrics.render().decode()


class TestObserve:
    def test_counts_each_request_by_method_route_and_status(self, request_metrics):
        request_metrics.observe("GET", "/posts/{post_id}", 200, 0.01)
        request_metrics.observe("GET", "/posts/{post_id}", 200, 0.02)
        request_metrics.observe("GET", "/posts/{post_id}", 404, 0.01)

        body = _render(request_metrics)
        ok = {"method": "GET", "route": "/posts/{post_id}", "status": "200"}
        missing = {**ok, "status": "404"}
        assert sample_value(body, "http_requests_total", **ok) == 2
        assert sample_value(body, "http_requests_total", **missing) == 1

    def test_records_latency_in_the_histogram(self, request_metrics):
        request_metrics.observe("POST", "/auth/login", 200, 0.3)

        body = _render(request_metrics)
        labels = {"method": "POST", "route": "/auth/login"}
        assert sample_value(body, "http_request_duration_seconds_count", **labels) == 1
        assert sample_value(body, "http_request_duration_seconds_sum", **labels) == 0.3
        assert sample_value(body, "http_request_duration_seconds_bucket", **labels, le="0.25") == 0
        assert sample_value(body, "http_request_duration_seconds_bucket", **labels, le="0.5") == 1

    def test_latency_has_no_status_label(self, request_metrics):
        """Status lives on the counter only: a histogram per status code
        multiplies the bucket series for little benefit."""
        request_metrics.observe("GET", "/health", 503, 0.01)

        families = {f.name: f for f in text_string_to_metric_families(_render(request_metrics))}
        sample = families["http_request_duration_seconds"].samples[0]
        assert "status" not in sample.labels


class TestBuckets:
    def test_sorted_and_positive(self):
        assert list(LATENCY_BUCKETS) == sorted(LATENCY_BUCKETS)
        assert all(bucket > 0 for bucket in LATENCY_BUCKETS)

    @pytest.mark.parametrize("seconds", [0.005, 10.0], ids=["fastest", "slowest"])
    def test_cover_the_expected_range(self, seconds):
        assert seconds in LATENCY_BUCKETS


class TestRegistry:
    def test_two_instances_cannot_share_a_registry(self, registry):
        """Why REQUEST_METRICS is a module-level singleton."""
        RequestMetrics(registry)
        with pytest.raises(ValueError, match="Duplicated timeseries"):
            RequestMetrics(registry)
