---
slug: domestic-relations-workflows
title: Domestic relations workflows
description: Organize family-law cases, parties, children, custody, support calculations, orders, payments, and deadlines.
order: 130
read_time: 9 min
icon: users
---

# Domestic relations workflows

The [Domestic Relations portfolio](/plugins/domestic/cases) tracks family-law cases: divorce, custody, child support, paternity, modifications, and protective orders. Use it alongside the controlling matter, the pleadings and orders, the financial evidence, and your jurisdiction's procedures. It is part of the domestic relations add-on; if you cannot open it, see [Add-on module management](/guide/add-on-module-management).

## Read the case portfolio

**Case Portfolio** counts **Active Cases**, **Pending** cases, the **Children** involved, and the total **Monthly Support** being tracked. Each row shows the case, its type, client, jurisdiction, children, monthly support, status, and **Next Deadline**. Search by case name or filter by status, and select **View** to open a case.

## Create a case

1. Select **New Case**.
2. Enter a **Case Name** that identifies the parties and the issue, such as "Doe v. Doe — Child Support".
3. Choose the **Type**: **Divorce**, **Custody**, **Child Support**, **Paternity**, **Modification**, **Protective Order**, or **Other**.
4. Enter the **State** (for example `ND`) and, optionally, the **County**.
5. Select **Create Case**.

## Work through the case tabs

- **Overview**: the court, case number, current support, the next deadline, and a **Case Summary** of the posture and key issues. Select **Save Summary** after editing it.
- **Parties**: each participant and their role in the proceeding (**Save Party**).
- **Children**: each child's name, date of birth, and any special needs (**Save Child**).
- **Custody**: current or proposed **Custody Arrangements**, legal and physical custody, and overnights.
- **Support Calculator**: a reviewable guideline calculation, described below.
- **Orders & Payments**: **Support Orders** with their effective dates and amounts, and the payments recorded against them (**Record Payment**), split between current support and arrears.
- **Deadlines**: procedural and court dates, with whether each was filed or served (**Save Deadline**).
- **Saved Calcs**: every calculation saved to the case, for comparison later.

Use verified names and the roles the proceeding uses. Avoid casual labels for parties or children.

## Calculate child support

1. Open **Support Calculator** and check the **State**.
2. Under **Calculation Inputs**, enter each parent's details under **Party A — Petitioner** and **Party B — Respondent**, including gross monthly income.
3. Choose the **Custody** arrangement: **Primary (one parent)**, **Equal / shared**, or **Split custody**, and enter the number of children.
4. The result recalculates as you type. The **Presumptive Monthly Support** and the **Worksheet** show how it was reached; read any **Warnings**.
5. If you depart from the guideline, enter the written basis under **Reason (required)**.
6. Name the run under **Save this run as…**, such as "Initial guideline calc", and select **Save to Case**.

To compare two sets of facts, select **Pin as Scenario A**, change the inputs, and read **Scenario B (current)** beside it with the **Difference**.

Check income periods, adjustments, parenting time, insurance, childcare, dependents, deviations, and jurisdiction-specific inputs. When material facts change, save a new calculation rather than overwriting the earlier one, so its context is preserved.

> [!IMPORTANT]
> A calculated amount is not a court order and may not reflect every statutory or factual issue. Label drafts as drafts and have them professionally reviewed.

## Sensitive information

Domestic cases can hold home addresses, financial records, health details, abuse allegations, and information about children. Follow sealing, redaction, protected-address, and access requirements. Do not expose restricted information through a general note, a portal invitation, an export, or an assistant prompt.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Calculation failed." | An input is missing or not a number | Check each parent's income and the custody inputs. |
| **Save to Case** is disabled | No worksheet has been calculated yet | Complete the inputs until a result appears, then save. |
| "Domestic Relations data could not be loaded" | The add-on is not available for your firm | Ask your administrator. |

## Related chapters

- [Add-on module management](/guide/add-on-module-management)
- [Mediation workflows](/guide/mediation-workflows)
- [Matters & documents](/guide/matters-and-documents)
