// Politicile VersoML (Cedar, evaluate cu cedarpy la fiecare apel de tool).
//
// Default deny: o cerere fără un `permit` potrivit e refuzată.
// Zidul anti-tipping-off (Legea 129/2019 art. 38 alin. 2, docs/05 §6.3 stratul 3) e scris ca `forbid`,
// iar în Cedar un `forbid` bate orice `permit`.
//
// Entitățile (principali, roluri, grupuri de tool-uri) sunt construite în versoml/shared/policy/entities.py.
// Orice modificare aici trebuie oglindită în evaluatorul de rezervă (fallback.py); testul de paritate o verifică.

// ------------------------------------------------------------------ zona client

@id("client-agents-tools")
permit (principal in Role::"client_agent", action in Action::"client_tools", resource == Zone::"client");

@id("operator-client-tools")
permit (principal == Human::"Operator", action in Action::"client_tools", resource == Zone::"client");

@id("motor-system-tools")
permit (
  principal == System::"MotorReguli",
  action in [Action::"ledger.read_client", Action::"diode.send_facts", Action::"letters.check_letter"],
  resource == Zone::"client"
);

// Singurul tool cu efect: rambursarea. Doar motorul de reguli, sub plafon sau după aprobare umană.
@id("motor-refund")
permit (principal == System::"MotorReguli", action == Action::"refund.issue", resource == Zone::"client")
when {
  (context has within_auto_cap && context.within_auto_cap == true) ||
  (context has approved_by_human && context.approved_by_human == true)
};

@id("mcp-client-tools")
permit (principal == Mcp::"client", action in Action::"mcp_client_tools", resource == Zone::"client");

// O semnătură pe decizia unui caz și o schimbare a parametrilor regulilor: operatorul uman, dintr-o sesiune
// semnată (serviciul verifică sesiunea și rolul ei înainte să întrebe).
@id("operator-signoff")
permit (
  principal == Human::"Operator",
  action in [Action::"cases.approve", Action::"rules.set_params"],
  resource == Zone::"client"
);

// ------------------------------------------------------------------ zona AML

@id("aml-agents-tools")
permit (principal in Role::"aml_agent", action in Action::"aml_tools", resource == Zone::"aml");

@id("analyst-aml-tools")
permit (principal == Human::"AnalistAML", action in Action::"analyst_tools", resource == Zone::"aml");

// Singurul semnal spre zona client: HOLD, emis de un om din consola AML.
@id("analyst-hold")
permit (principal == Human::"AnalistAML", action == Action::"diode.send_hold", resource == Zone::"aml");

@id("mcp-aml-tools")
permit (principal == Mcp::"aml", action in Action::"mcp_aml_tools", resource == Zone::"aml");

// ------------------------------------------------------------------ zidul (forbid bate permit)

@id("wall-client-not-in-aml")
forbid (principal, action, resource == Zone::"aml")
when { principal has zone && principal.zone == "client" };

@id("wall-aml-not-in-client")
forbid (principal, action, resource == Zone::"client")
when { principal has zone && principal.zone == "aml" };

@id("wall-client-no-aml-actions")
forbid (principal, action in Action::"aml_zone", resource)
when { principal has zone && principal.zone == "client" };

@id("wall-aml-no-client-actions")
forbid (principal, action in Action::"client_zone", resource)
when { principal has zone && principal.zone == "aml" };

@id("refund-only-motor")
forbid (principal, action == Action::"refund.issue", resource)
unless { principal == System::"MotorReguli" };

@id("no-llm-moves-money")
forbid (principal in Role::"llm_agent", action in Action::"client_effects", resource);

@id("hold-only-analyst")
forbid (principal, action == Action::"diode.send_hold", resource)
unless { principal == Human::"AnalistAML" };

@id("facts-only-from-client")
forbid (principal, action == Action::"diode.send_facts", resource)
unless { principal has zone && principal.zone == "client" };

@id("mcp-no-effects")
forbid (principal is Mcp, action in [Action::"client_effects", Action::"diode"], resource);

// Doar un om semnează. Un client MCP sau un agent LLM poate propune o decizie (mcp.cases.propose), nu o aprobă.
@id("only-a-person-signs")
forbid (principal, action in Action::"signoff", resource)
unless { principal is Human };
