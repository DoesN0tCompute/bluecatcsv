"""Data models for the BlueCat CSV Importer."""

from .csv_row import (
    CSVRow,
    CSVRowBase,
    HostRecordRow,
    IP4AddressRow,
    IP4BlockRow,
    IP4NetworkRow,
    IPv4DHCPRangeRow,
)
from .operations import FieldChange, Operation, OperationStatus, OperationType
from .results import DiffResult, ImportResult, OperationResult, RollbackManifest
from .state import ResourceIdentifier, ResourceState, StateLoadStrategy

__all__ = [
    # CSV Rows
    "CSVRow",
    "CSVRowBase",
    "IP4NetworkRow",
    "IP4BlockRow",
    "IP4AddressRow",
    "HostRecordRow",
    "DNSZoneRow",
    # DHCP Rows
    "IPv4DHCPRangeRow",
    # Operations
    "Operation",
    "OperationType",
    "OperationStatus",
    "FieldChange",
    # State
    "ResourceState",
    "ResourceIdentifier",
    "StateLoadStrategy",
    # Results
    "DiffResult",
    "OperationResult",
    "ImportResult",
    "RollbackManifest",
]
