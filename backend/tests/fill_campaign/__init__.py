"""Smart Fill quirk campaign.

A reproducible harness that runs the matter-data resolver over mock matters and
mock (and real, seeded) documents, renders the result through the production
PDF and DOCX writers, reads the values back, and reports what filled, from
where, and what stayed blank without saying so.

The package is test support: nothing here is imported by the application.
``scripts/rehearse_smart_fill.py`` reuses it to print the quirk report.
"""
