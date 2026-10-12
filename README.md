# IT Service Management

Native Frappe/ERPNext custom application for IT retail, equipment lifecycle, service contracts, field service, and rental operations.

This repository contains four native Frappe/ERPNext implementation phases:

Phase 1 foundations:

- App skeleton and modules
- IT Service Settings
- Customer Site
- Customer Equipment
- Warranty Policy
- Service Plan
- Service Contract
- Service Contract Equipment
- Service Contract Entitlement
- ServiceEntitlementEngine
- Basic roles, workspace, hooks, and tests

Phase 2 service operations:

- Service Ticket, Service Job, dispatch, labour, parts, expenses, and remote support
- SLA, entitlement, service charging, billing preparation, stock consumption, reports, and tests

Phase 3 rental operations:

- Rental plans, contracts, deployments, replacements, returns, inspections, and preventive maintenance
- Extensible equipment meter readings, controlled resets, Decimal-safe usage billing, and proration
- Consolidated or supplemental billing runs with draft Sales Invoices and duplicate-billing references
- ERPNext Asset, Serial No, Subscription, Customer Equipment, Service Job, and Sales Invoice integration
- Rental workflows, roles, notifications, scheduled checks, workspace, reports, and automated tests

Phase 4 finance controls and management analytics:

- Approval-controlled service and rental billing with source-level duplicate prevention and cancellation recovery
- Subscription reconciliation, recurring billing, unbilled revenue, leakage, profitability, utilisation, and period-end reports
- Service and rental contract renewal opportunities with duplicate-safe scheduled discovery
- Customer, equipment, contract, technician, SLA, warranty, and data-quality analytics
- Native Customer, Customer Equipment, Serial No, and Asset dashboard links
- Service Command Center, Rental Command Center, and IT Services Executive workspaces
- Read-only Analyst and Executive roles, short-lived dashboard caching, reporting indexes, and Phase 4 tests

Email ticketing:

- Configure ERPNext Email Account with `Append To` set to `Service Ticket`.
- Set fallback email defaults in `IT Service Settings`: customer, ticket type, and priority.
- The app sends a Service Ticket email acknowledgement through the standard Notification fixture.
- Customer replies to the acknowledgement normally follow ERPNext email threading. If a reply is imported as a new Service Ticket, the app detects the existing ticket ID in the subject/body, appends the reply to that ticket, and cancels the duplicate reply ticket.

Hire Purchase and external frontends are intentionally out of scope.
