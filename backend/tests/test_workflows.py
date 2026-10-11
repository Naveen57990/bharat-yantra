"""Deterministic smoke tests for the local Bharat Yantra data workflows.

These tests use the repository's checked-in local extracts. They do not call
external services and do not treat outputs as validated real-world impacts.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.app import accessibility, decisions, flood, flood_runs, investments, main, preparedness


class InputValidationTests(unittest.TestCase):
    def test_rainfall_rejects_zero_and_excessive_duration(self) -> None:
        with self.assertRaises(ValidationError):
            flood.RainfallScenarioRequest(rainfall_mm=0, duration_hours=8)
        with self.assertRaises(ValidationError):
            flood.RainfallScenarioRequest(rainfall_mm=100, duration_hours=169)

    def test_access_request_rejects_out_of_range_coordinates(self) -> None:
        with self.assertRaises(ValidationError):
            accessibility.FacilityRoutesRequest(longitude=190, latitude=19)

    def test_investment_rejects_zero_allowance(self) -> None:
        with self.assertRaises(ValidationError):
            investments.InvestmentPlanRequest(
                budget_crore=1,
                drainage_site_allowance_inr=0,
                streetlight_site_allowance_inr=50000,
                health_access_site_allowance_inr=50000,
            )


class ApiContractTests(unittest.TestCase):
    def test_critical_api_routes_are_registered(self) -> None:
        routes = {
            (method, route.path)
            for route in main.app.routes
            for method in (getattr(route, "methods", None) or set())
        }
        expected = {
            ("GET", "/api/v1/health"),
            ("GET", "/api/v1/datasets"),
            ("GET", "/api/v1/accessibility/closure-options"),
            ("POST", "/api/v1/accessibility/routes"),
            ("POST", "/api/v1/accessibility/runs"),
            ("POST", "/api/v1/flood/screening-scenario"),
            ("POST", "/api/v1/preparedness/plans"),
            ("POST", "/api/v1/investments/compare"),
            ("POST", "/api/v1/decisions"),
            ("GET", "/api/v1/agent/status"),
        }
        self.assertTrue(expected.issubset(routes))

    def test_health_and_registry_handlers_report_readiness_honestly(self) -> None:
        with patch.object(main, "local_model_status", return_value={"ready": False}):
            status = main.health()
        self.assertEqual(status.status, "ready")
        self.assertTrue(status.exploratory_accessibility_available)
        self.assertFalse(status.flood_simulation_outputs_available)
        self.assertFalse(status.ai_agent_enabled)
        datasets = main.get_dataset_status()
        self.assertEqual(len(datasets), 19)
        self.assertTrue(all(item.publication_status == "hold" for item in datasets))


class RealDataWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.run_dir = Path(self.tempdir.name)
        self.patches = [
            patch.object(accessibility, "RUNS_PATH", self.run_dir / "access"),
            patch.object(flood_runs, "RUNS_PATH", self.run_dir / "flood"),
            patch.object(investments, "RUNS_PATH", self.run_dir / "investment"),
            patch.object(preparedness, "RUNS_PATH", self.run_dir / "preparedness"),
            patch.object(decisions, "RUNS_PATH", self.run_dir / "decisions"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_rainfall_calculation_and_saved_record(self) -> None:
        request = flood.RainfallScenarioRequest(rainfall_mm=150, duration_hours=8)
        result = flood.calculate_rainfall_scenario(request)
        self.assertEqual(result["mean_intensity_mm_per_hour"], 18.75)
        expected_volume = round(150 / 1000 * flood._ward_area_m2())
        self.assertEqual(result["gross_rainfall_volume_m3"], expected_volume)
        self.assertIn("flood depth", result["interpretation"])
        self.assertIn("not runoff", result["interpretation"])

        evidence_area = flood.flood_evidence()["ward"]["area_km2"]
        displayed_volume = round(request.rainfall_mm * evidence_area * 1000)
        self.assertEqual(displayed_volume, result["gross_rainfall_volume_m3"])

        saved = flood_runs.create_rainfall_run(request)
        reread = flood_runs.read_flood_run(saved.run_id)
        self.assertEqual(reread.inputs, saved.inputs)
        self.assertEqual(reread.outputs["gross_rainfall_volume_m3"], expected_volume)
        with self.assertRaises(HTTPException) as error:
            flood_runs.read_flood_run("not-a-run-id")
        self.assertEqual(error.exception.status_code, 404)

    def test_facility_routes_and_outside_ward_error(self) -> None:
        response = accessibility.get_nearby_facility_routes(
            accessibility.FacilityRoutesRequest(
                longitude=72.8490653, latitude=18.9983119, radius_m=5000
            )
        )
        self.assertGreater(response.facilities_found, 0)
        self.assertEqual(len(response.routes_geojson["features"]), response.facilities_found)
        self.assertGreaterEqual(response.facilities[0]["distance_m"], 0)
        self.assertIn("not travel time", " ".join(response.assumptions))
        with self.assertRaises(HTTPException) as error:
            accessibility.get_nearby_facility_routes(
                accessibility.FacilityRoutesRequest(longitude=0, latitude=0)
            )
        self.assertEqual(error.exception.status_code, 422)

    def test_hypothetical_closure_reduces_or_preserves_connectivity_and_saves(self) -> None:
        options = accessibility.get_closure_options()
        self.assertTrue(any(option.road_name == "Acharya Donde Marg" for option in options))
        result = accessibility.run_road_closure("Acharya Donde Marg")
        self.assertGreater(result.closed_directed_edges, 0)
        self.assertLessEqual(
            result.scenario.route_coverage_percent,
            result.baseline.route_coverage_percent,
        )
        self.assertGreaterEqual(result.change["newly_unreachable_road_nodes"], 0)
        self.assertGreater(len(result.closed_edges_geojson["features"]), 0)
        self.assertEqual(accessibility.read_access_run(result.run_id).road_name, "Acharya Donde Marg")
        saved_decision = decisions.create_decision_record(
            decisions.DecisionSaveRequest(
                decision_type="road_closure", source_run_id=result.run_id
            )
        )
        reread_decision = decisions.read_decision_record(saved_decision["decision_id"])
        self.assertEqual(reread_decision["source_run_id"], result.run_id)
        self.assertEqual(
            reread_decision["outputs"]["measured_change"]["newly_unreachable_road_nodes"],
            result.change["newly_unreachable_road_nodes"],
        )
        with self.assertRaises(HTTPException) as error:
            accessibility.run_road_closure("Road Not In The Dataset")
        self.assertEqual(error.exception.status_code, 422)

    def test_investment_costs_respect_budget_and_return_mapped_options(self) -> None:
        request = investments.InvestmentPlanRequest(
            budget_crore=1,
            drainage_site_allowance_inr=100000,
            streetlight_site_allowance_inr=50000,
            health_access_site_allowance_inr=75000,
            streetlight_spacing_m=100,
        )
        result = investments.create_investment_plan(request)
        self.assertEqual(len(result["options"]), 3)
        budget = result["inputs"]["budget_inr"]
        for option in result["options"]:
            self.assertLessEqual(option["estimated_cost_inr"], budget)
            self.assertEqual(
                option["planned_count"],
                len(option["feature_collection"]["features"]),
            )
            self.assertGreaterEqual(option["remaining_budget_inr"], 0)

    def test_preparedness_scenarios_return_mapped_checks_within_budget(self) -> None:
        request = preparedness.PreparednessPlanRequest(
            rainfall_mm=150,
            duration_hours=8,
            budget_crore=1,
            cell_review_rate_inr=100000,
            record_verification_rate_inr=50000,
            shelter_audit_rate_inr=75000,
        )
        result = preparedness.create_preparedness_plan(request)
        self.assertTrue(result["options"])
        self.assertTrue(any(option["mapped_actions"] > 0 for option in result["options"]))
        for option in result["options"]:
            self.assertLessEqual(option["estimated_allocation_inr"], result["inputs"]["budget_inr"])

        longer = preparedness.create_preparedness_plan(
            request.model_copy(update={"duration_hours": 16})
        )
        self.assertGreaterEqual(
            longer["rainfall_screening"]["field_check_locations_shown"],
            result["rainfall_screening"]["field_check_locations_shown"],
        )


if __name__ == "__main__":
    unittest.main()
