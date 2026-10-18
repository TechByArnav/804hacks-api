from __future__ import annotations

import re
import math
from dataclasses import dataclass
from typing import Any


@dataclass
class LanguageProfile:
    base_watts_per_million_ops: float
    memory_watts_per_gb: float
    cpu_intensity_factor: float
    typical_ipc: float


LANGUAGE_PROFILES = {
    "python": LanguageProfile(
        base_watts_per_million_ops=15.0,
        memory_watts_per_gb=0.8,
        cpu_intensity_factor=1.3,
        typical_ipc=0.5,
    ),
    "javascript": LanguageProfile(
        base_watts_per_million_ops=12.0,
        memory_watts_per_gb=0.7,
        cpu_intensity_factor=1.1,
        typical_ipc=0.7,
    ),
    "typescript": LanguageProfile(
        base_watts_per_million_ops=12.0,
        memory_watts_per_gb=0.7,
        cpu_intensity_factor=1.1,
        typical_ipc=0.7,
    ),
    "java": LanguageProfile(
        base_watts_per_million_ops=10.0,
        memory_watts_per_gb=0.9,
        cpu_intensity_factor=0.9,
        typical_ipc=1.2,
    ),
    "go": LanguageProfile(
        base_watts_per_million_ops=8.0,
        memory_watts_per_gb=0.6,
        cpu_intensity_factor=0.7,
        typical_ipc=1.5,
    ),
    "rust": LanguageProfile(
        base_watts_per_million_ops=7.0,
        memory_watts_per_gb=0.5,
        cpu_intensity_factor=0.6,
        typical_ipc=1.8,
    ),
    "cpp": LanguageProfile(
        base_watts_per_million_ops=7.0,
        memory_watts_per_gb=0.5,
        cpu_intensity_factor=0.6,
        typical_ipc=2.0,
    ),
    "c": LanguageProfile(
        base_watts_per_million_ops=6.0,
        memory_watts_per_gb=0.4,
        cpu_intensity_factor=0.5,
        typical_ipc=2.2,
    ),
    "csharp": LanguageProfile(
        base_watts_per_million_ops=9.0,
        memory_watts_per_gb=0.8,
        cpu_intensity_factor=0.9,
        typical_ipc=1.3,
    ),
    "ruby": LanguageProfile(
        base_watts_per_million_ops=18.0,
        memory_watts_per_gb=0.9,
        cpu_intensity_factor=1.4,
        typical_ipc=0.4,
    ),
    "php": LanguageProfile(
        base_watts_per_million_ops=16.0,
        memory_watts_per_gb=0.8,
        cpu_intensity_factor=1.2,
        typical_ipc=0.6,
    ),
}


class CodeEnergyEstimator:
    def __init__(self):
        self.idle_watts = 5.0
        self.cpu_tdp_watts = 65.0
        self.memory_watts_per_gb = 0.375

    def estimate(
        self,
        code: str,
        language: str,
        runtime_seconds: float | None,
        cpu_utilization: float,
        memory_mb: float,
        carbon_intensity_g_per_kwh: float,
    ) -> dict[str, Any]:
        lang = language.lower()
        profile = LANGUAGE_PROFILES.get(lang, LANGUAGE_PROFILES["python"])

        complexity = self._analyze_complexity(code, lang)
        estimated_ops = self._estimate_operations(code, complexity, lang)

        if runtime_seconds is None:
            runtime_seconds = self._estimate_runtime(estimated_ops, profile)

        cpu_energy = self._calculate_cpu_energy(
            runtime_seconds, cpu_utilization, profile
        )
        memory_energy = self._calculate_memory_energy(memory_mb, runtime_seconds)
        base_energy = self.idle_watts * runtime_seconds / 3600.0

        total_energy_wh = cpu_energy + memory_energy + base_energy
        total_energy_kwh = total_energy_wh / 1000.0

        emissions_g = total_energy_kwh * carbon_intensity_g_per_kwh
        emissions_lb = emissions_g / 453.592

        breakdown = {
            "cpu_wh": round(cpu_energy, 3),
            "memory_wh": round(memory_energy, 3),
            "idle_wh": round(base_energy, 3),
            "total_wh": round(total_energy_wh, 3),
            "estimated_operations": estimated_ops,
            "estimated_runtime_seconds": round(runtime_seconds, 2),
            "complexity_score": complexity,
            "language": lang,
        }

        return {
            "energy_kwh": round(total_energy_kwh, 6),
            "emissions_g_co2": round(emissions_g, 3),
            "emissions_lb_co2": round(emissions_lb, 6),
            "breakdown": breakdown,
        }

    def _analyze_complexity(self, code: str, language: str) -> float:
        lines = code.split("\n")
        non_empty = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]

        if not non_empty:
            return 1.0

        loops = len(re.findall(r"\b(for|while)\b", code))
        nested_loops = len(re.findall(r"\b(for|while)\b.*\b(for|while)\b", code, re.DOTALL))
        recursion = len(re.findall(r"\bdef\s+(\w+).*\b\1\s*\(", code, re.DOTALL))
        function_calls = len(re.findall(r"\w+\s*\(", code))
        comprehensions = len(re.findall(r"\[.*for.*in.*\]", code))
        generators = len(re.findall(r"\(.*for.*in.*\)", code))

        complexity = 1.0
        complexity += loops * 0.5
        complexity += nested_loops * 2.0
        complexity += recursion * 3.0
        complexity += function_calls * 0.1
        complexity += comprehensions * 0.3
        complexity += generators * 0.2
        complexity += len(non_empty) * 0.01

        if language in ("python", "ruby", "php"):
            complexity *= 1.3
        elif language in ("go", "rust", "c", "cpp"):
            complexity *= 0.7

        return max(1.0, complexity)

    def _estimate_operations(self, code: str, complexity: float, language: str) -> int:
        lines = len([l for l in code.split("\n") if l.strip()])
        base_ops_per_line = {
            "python": 5000000,
            "javascript": 8000000,
            "typescript": 8000000,
            "java": 10000000,
            "go": 15000000,
            "rust": 18000000,
            "cpp": 20000000,
            "c": 25000000,
            "csharp": 10000000,
            "ruby": 4000000,
            "php": 6000000,
        }.get(language.lower(), 5000000)

        return int(lines * base_ops_per_line * complexity)

    def _estimate_runtime(self, operations: int, profile: LanguageProfile) -> float:
        ops_per_second = 2.5e9 * profile.typical_ipc / profile.cpu_intensity_factor
        runtime = operations / ops_per_second
        return max(runtime, 0.001)

    def _calculate_cpu_energy(
        self, runtime_seconds: float, utilization: float, profile: LanguageProfile
    ) -> float:
        active_watts = self.cpu_tdp_watts * utilization * profile.cpu_intensity_factor
        return active_watts * runtime_seconds / 3600.0

    def _calculate_memory_energy(self, memory_mb: float, runtime_seconds: float) -> float:
        memory_gb = memory_mb / 1024.0
        return self.memory_watts_per_gb * memory_gb * runtime_seconds / 3600.0

    def compare_optimizations(
        self,
        original_code: str,
        optimized_code: str,
        language: str,
        carbon_intensity_g_per_kwh: float,
    ) -> dict[str, Any]:
        original = self.estimate(
            original_code, language, None, 0.5, 256, carbon_intensity_g_per_kwh
        )
        optimized = self.estimate(
            optimized_code, language, None, 0.5, 256, carbon_intensity_g_per_kwh
        )

        energy_saved = original["energy_kwh"] - optimized["energy_kwh"]
        emissions_saved = original["emissions_g_co2"] - optimized["emissions_g_co2"]
        pct_reduction = (
            (energy_saved / original["energy_kwh"] * 100) if original["energy_kwh"] > 0 else 0
        )

        return {
            "original": original,
            "optimized": optimized,
            "savings": {
                "energy_kwh": round(energy_saved, 6),
                "emissions_g_co2": round(emissions_saved, 3),
                "emissions_lb_co2": round(emissions_saved / 453.592, 6),
                "percent_reduction": round(pct_reduction, 1),
            },
        }