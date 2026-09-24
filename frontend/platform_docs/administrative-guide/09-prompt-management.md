---
slug: prompt-management
title: Prompt management
description: Review, test, override, and restore the instructions that LawHand's AI skills follow, without weakening their safeguards.
order: 90
read_time: 8 min
icon: sparkles
---

# Prompt management

[Prompts](/admin?tab=prompts) lets you replace the instructions a supported AI skill follows for your whole firm. A saved override takes effect immediately, across every matter that uses the skill, so treat it as a production change.

**Prompts** appears only for administrators with the `admin_settings` capability, and is marked **ADV** in the tab bar.

## Find the skill

1. Open [Prompts](/admin?tab=prompts).
2. In the tree, expand the add-on and select the skill. Skills with an override show **Active**.
3. Read the **Default Prompt (read-only)**: the platform's own instructions, which apply when there is no override.

Prefer the default whenever it meets your firm's needs. Every override makes it harder to adopt later platform improvements.

## Write an override

1. In the override box, write the full instructions the skill should follow. Leaving it empty uses the default.
2. Keep every template variable the default relies on. Open **Template Variables** to insert one:

   | Variable | Supplies |
   | --- | --- |
   | `{work_product_header}` | The attorney work product disclaimer badge |
   | `{universal_guardrails}` | The universal citation and ethics rules |
   | `{practice_profile}` | Your firm's practice profile |
   | `{matter_context}` | The current matter's context |
   | `{dsar_context}` | Data subject request details |
   | `{jurisdiction}` | The jurisdiction |
   | `{chart_mode}` | The chart mode: infringement, invalidity, or civil elements |

3. Describe the structure, firm terminology, jurisdictional constraints, and review expectations you want.

> [!CAUTION]
> Never remove `{universal_guardrails}` or instruct the model to invent citations, hide uncertainty, bypass permissions, send external messages on its own, or skip review steps. Never put client facts, credentials, tokens, infrastructure details, or one matter's strategy in a firm-wide prompt.

## Test before saving

1. Enter redacted, representative input in the test box and select **Run Test**. The **Response** shows the output, the model used, and the tokens consumed.
2. Test normal, missing-information, ambiguous, and adverse cases.
3. Check the required sections and formatting, the use of sources and citations, how uncertainty is flagged, protection against unsupported conclusions, the token and time cost, and that the output still works with the review and export steps that follow.

Record the reason for the change, its owner, the test cases, who approved it, and how you would roll it back.

## Save, and roll back if needed

1. Make sure **Override active** is on, and select **Save Override** (or **Update Override** for an existing one). "Override saved. Skills will use the custom prompt immediately."
2. Run a small real-world check with non-sensitive content.

To go back to the platform instructions, select **Reset to Default**, then **Yes, Reset**. "Override removed. Code default restored." Check that the default text is showing, and test again.

If an override produces unsafe or unusable output, reset it or restore the last approved text at once, then keep the examples and request IDs for investigation. When the platform default changes in a release, review whether your override is still needed.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Prompts** is not in the tab bar | You lack the `admin_settings` capability | Ask an administrator who holds it. |
| Output lost its disclaimer or citation rules | The override removed `{work_product_header}` or `{universal_guardrails}` | Add the variables back, test, and save. |
| "No default prompt configured for this skill." | The skill has no platform instructions to show | Contact LawHand support before writing an override. |
| "Test failed" | The prompt or input could not be processed | Check the variables and input, and try again. |

## Related chapters

- [AI, search & MCP](/admin?tab=guide&chapter=ai-search-and-mcp)
- [Administrator overview](/admin?tab=guide&chapter=admin-overview)
- [Add-on module management](/guide/add-on-module-management)
