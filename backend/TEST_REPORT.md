# QuoteFlow — Automated Testing Report

Generated 2026-10-31 00:28 UTC by `python scripts/test_report.py`.

## Summary

| Metric | Value |
| --- | --- |
| Total test cases | **470** |
| Passed | **470** |
| Failed | **0** |
| Skipped | 0 |
| Pass rate | 100.0% |
| Execution time | 644.1 s |

All tests passed.

## Results by area

| Area | Cases | Passed | Failed | Time |
| --- | --- | --- | --- | --- |
| Analytics, audit trail and settings | 27 | 27 | 0 | 27.7 s |
| Authentication and access control | 25 | 25 | 0 | 15.6 s |
| Catalogue, products and customers | 32 | 32 | 0 | 22.6 s |
| Discount rule engine (pure policy) | 35 | 35 | 0 | 0.8 s |
| End-to-end demonstration scenarios | 13 | 13 | 0 | 358.1 s |
| Failure handling and idempotency | 33 | 33 | 0 | 32.6 s |
| Manager approvals | 23 | 23 | 0 | 26.3 s |
| Pricing engine (pure arithmetic) | 16 | 16 | 0 | 0.4 s |
| Quotations, PDF and verification | 19 | 19 | 0 | 14.3 s |
| Request state machine and money helpers | 39 | 39 | 0 | 0.8 s |
| Security (auth, RBAC, passwords, downloads, config) | 67 | 67 | 0 | 35.3 s |
| Workflow boundaries (retries, gate, no-op, escalation, budget) | 47 | 47 | 0 | 28.4 s |
| Workflow pipeline | 46 | 46 | 0 | 37.4 s |
| Master-data authorisation (manager approval) | 48 | 48 | 0 | 42.9 s |

## Test case results

### Analytics, audit trail and settings

`tests/test_analytics_and_audit.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the overview counts requests and value | 2.51 s |
| PASS | test the overview is safe on an empty database | 0.83 s |
| PASS | test the discount rate is measured against gross value | 1.71 s |
| PASS | test the request trend is bucketed by day | 1.62 s |
| PASS | test top products ranks by value | 1.42 s |
| PASS | test top customers reports quoted value | 1.24 s |
| PASS | test the exception breakdown shows what drives manual review | 1.22 s |
| PASS | test workflow performance reports the automation rate | 1.45 s |
| PASS | test approval performance measures turnaround | 1.28 s |
| PASS | test approval performance is safe with nothing decided | 0.56 s |
| PASS | test the dashboard returns every section | 1.27 s |
| PASS | test the workflow writes an audit trail | 1.23 s |
| PASS | test audit entries name the actor | 1.26 s |
| PASS | test an approval decision is audited | 1.30 s |
| PASS | test a product update records a field level diff | 1.12 s |
| PASS | test a download is audited | 1.26 s |
| PASS | test a public verification is audited | 1.27 s |
| PASS | test the audit trail has no write endpoints | 0.03 s |
| PASS | test retuning the tier table changes the outcome | 1.30 s |
| PASS | test a nested patch does not wipe its siblings | 0.60 s |
| PASS | test an invalid tier table is rejected | 0.58 s |
| PASS | test a tax change applies to the next request | 1.25 s |
| PASS | test the discount policy endpoint summarises the limits | 0.58 s |
| PASS | test a settings change is audited | 0.59 s |
| PASS | test the health endpoint reports the database | 0.03 s |
| PASS | test the service banner is public | 0.03 s |
| PASS | test the openapi schema is served | 0.18 s |

### Authentication and access control

`tests/test_auth.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test registration creates a user and a customer record | 0.31 s |
| PASS | test registration rejects a duplicate email | 0.32 s |
| PASS | test registration enforces a minimum password length | 0.03 s |
| PASS | test password is never returned or stored in clear | 0.30 s |
| PASS | test login succeeds and records the timestamp | 0.56 s |
| PASS | test login with a wrong password is rejected | 0.56 s |
| PASS | test login with an unknown email gives the same error | 0.54 s |
| PASS | test suspended account cannot sign in | 0.56 s |
| PASS | test suspension takes effect on an already issued token | 0.58 s |
| PASS | test refresh token yields a new access token | 0.58 s |
| PASS | test an access token is not accepted as a refresh token | 0.56 s |
| PASS | test a garbage token is rejected | 0.04 s |
| PASS | test missing credentials are rejected | 0.04 s |
| PASS | test me returns the linked customer for a customer account | 0.58 s |
| PASS | test me has no customer for staff | 0.57 s |
| PASS | test password change invalidates the old password | 1.62 s |
| PASS | test password change requires the current password | 0.84 s |
| PASS | test manager can create staff accounts | 0.83 s |
| PASS | test employee cannot create staff accounts | 0.57 s |
| PASS | test staff endpoint will not mint a customer account | 0.56 s |
| PASS | test customer cannot reach staff only endpoints | 0.58 s |
| PASS | test employee cannot reach manager only endpoints | 0.61 s |
| PASS | test every role may read the rule book | 1.63 s |
| PASS | test only a manager may change the rule book | 1.14 s |
| PASS | test me returns the same customer shape as the customer endpoints | 1.13 s |

### Catalogue, products and customers

`tests/test_catalogue.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the catalogue hides discontinued products | 0.59 s |
| PASS | test the catalogue hides cost price from customers | 0.58 s |
| PASS | test staff do see cost price | 0.57 s |
| PASS | test the catalogue shows the discount a customer may request | 0.58 s |
| PASS | test a gold customer sees their tier bonus | 0.58 s |
| PASS | test a product cap lowers the figure shown | 0.58 s |
| PASS | test low stock is flagged | 0.58 s |
| PASS | test the catalogue can be searched and filtered | 0.61 s |
| PASS | test the catalogue paginates | 0.59 s |
| PASS | test the availability check reports each line | 0.61 s |
| PASS | test everything in stock reports all available | 0.58 s |
| PASS | test the availability check 404s on an unknown product | 0.58 s |
| PASS | test a manager can create a product and the sku is normalised | 0.57 s |
| PASS | test an employee cannot create a product directly | 0.57 s |
| PASS | test a duplicate sku is a conflict | 0.59 s |
| PASS | test a customer cannot create a product | 0.58 s |
| PASS | test a zero unit price is rejected | 0.56 s |
| PASS | test reserved stock cannot exceed stock | 0.67 s |
| PASS | test a stock movement is applied | 0.60 s |
| PASS | test stock cannot be driven negative | 0.60 s |
| PASS | test stock cannot fall below the reserved quantity | 0.58 s |
| PASS | test deleting a product only discontinues it | 0.60 s |
| PASS | test an employee cannot discontinue a product | 0.59 s |
| PASS | test an unknown product is a 404 | 0.59 s |
| PASS | test a manager can create a customer with a generated code | 0.60 s |
| PASS | test a duplicate customer email is a conflict | 0.60 s |
| PASS | test an employee cannot create a customer directly | 0.58 s |
| PASS | test a customer can be updated | 1.17 s |
| PASS | test only a manager can block a customer | 1.70 s |
| PASS | test the customer summary reports activity | 1.30 s |
| PASS | test an issued quotation consumes credit | 1.30 s |
| PASS | test customers can be searched | 1.19 s |

### Discount rule engine (pure policy)

`tests/test_discount_engine.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test quantity bands from the brief[1-2.00] | 0.02 s |
| PASS | test quantity bands from the brief[5-2.00] | 0.02 s |
| PASS | test quantity bands from the brief[6-5.00] | 0.02 s |
| PASS | test quantity bands from the brief[20-5.00] | 0.02 s |
| PASS | test quantity bands from the brief[21-10.00] | 0.03 s |
| PASS | test quantity bands from the brief[50-10.00] | 0.02 s |
| PASS | test quantity bands from the brief[51-15.00] | 0.02 s |
| PASS | test quantity bands from the brief[10000-15.00] | 0.02 s |
| PASS | test discount at the ceiling is allowed | 0.03 s |
| PASS | test a hair over the ceiling needs approval | 0.02 s |
| PASS | test zero discount is always allowed | 0.02 s |
| PASS | test tier bonus raises the ceiling[STANDARD-5.00] | 0.03 s |
| PASS | test tier bonus raises the ceiling[SILVER-6.00] | 0.03 s |
| PASS | test tier bonus raises the ceiling[GOLD-7.00] | 0.03 s |
| PASS | test tier bonus raises the ceiling[PLATINUM-8.00] | 0.03 s |
| PASS | test gold customer gets a discount a standard customer would not | 0.03 s |
| PASS | test unknown tier receives no bonus | 0.03 s |
| PASS | test product cap clamps a generous band | 0.03 s |
| PASS | test product cap above the band does not raise the ceiling | 0.02 s |
| PASS | test absolute maximum is rejected outright | 0.02 s |
| PASS | test at the absolute maximum it is only an approval | 0.02 s |
| PASS | test discount below cost price is rejected | 0.03 s |
| PASS | test discount exactly at cost price is permitted | 0.02 s |
| PASS | test cost floor can be switched off by policy | 0.02 s |
| PASS | test zero cost price disables the floor check | 0.02 s |
| PASS | test override replaces the requested discount | 0.02 s |
| PASS | test override within policy clears the exception | 0.02 s |
| PASS | test override beyond the absolute maximum is rejected | 0.03 s |
| PASS | test override of zero is honoured not ignored | 0.02 s |
| PASS | test a reconfigured tier table changes the outcome | 0.02 s |
| PASS | test tiers are sorted on construction | 0.02 s |
| PASS | test an empty tier table is rejected | 0.03 s |
| PASS | test a tier with an inverted band is rejected | 0.02 s |
| PASS | test a quantity in no band gets no discount | 0.02 s |
| PASS | test quantity must be positive | 0.02 s |

### End-to-end demonstration scenarios

`tests/test_end_to_end_scenarios.py`

**TestScenario1SuccessfulQuotation**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the whole journey | 1.31 s |

**TestScenario2InvalidInput**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a discontinued product stops the workflow | 1.20 s |
| PASS | test missing customer information is detected | 0.62 s |
| PASS | test a malformed payload never reaches the workflow | 0.60 s |

**TestScenario3ExcessiveDiscount**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the request is sent to a manager | 0.66 s |
| PASS | test a manager approval then completes it | 1.32 s |
| PASS | test an override reprices the document | 1.32 s |

**TestScenario4ManagerRejection**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test rejection updates the status appropriately | 1.25 s |
| PASS | test a modification request returns it to the customer | 1.35 s |

**TestScenario5TemporaryFailure**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a transient fault recovers within the limit | 1.32 s |
| PASS | test a fault that never clears stops at the limit | 1.23 s |
| PASS | test a document fault escalates without issuing anything | 344.68 s |
| PASS | test a verification mismatch withholds the document | 1.20 s |

### Failure handling and idempotency

`tests/test_failure_handling.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test 1 missing customer information | 1.49 s |
| PASS | test 2 invalid product id | 0.85 s |
| PASS | test 2b malformed product id | 0.85 s |
| PASS | test 2c a product discontinued after drafting | 0.86 s |
| PASS | test 3 invalid quantity is rejected by the schema[0] | 0.79 s |
| PASS | test 3 invalid quantity is rejected by the schema[-5] | 0.78 s |
| PASS | test 3b a quantity past the ceiling fails validation | 1.57 s |
| PASS | test 4 product unavailable escalates to a manager | 0.60 s |
| PASS | test 4b product unavailable fails when backorders are off | 1.14 s |
| PASS | test 5 excessive discount goes to a manager | 0.60 s |
| PASS | test 5b a discount beyond any approval is refused | 0.60 s |
| PASS | test 5c a discount below cost is refused | 0.66 s |
| PASS | test 6 a database fault is retried then succeeds | 0.76 s |
| PASS | test 6b a persistent database fault escalates | 1.55 s |
| PASS | test 7 a request can only ever hold one quotation | 0.75 s |
| PASS | test 7b the unique index refuses a second quotation | 0.92 s |
| PASS | test 7c the action tool is idempotent | 1.00 s |
| PASS | test 7d a duplicate line is refused | 0.72 s |
| PASS | test 8 manager rejection updates the status | 1.24 s |
| PASS | test 8b rejection without a reason is refused | 1.16 s |
| PASS | test 9 a pdf failure is retried then escalates | 1.58 s |
| PASS | test 9b a pdf that writes nothing is caught | 1.09 s |
| PASS | test 10 a tampered total fails verification | 0.94 s |
| PASS | test 10b a tampered unit price fails verification | 0.97 s |
| PASS | test 10c a mismatch escalates rather than completing | 1.70 s |
| PASS | test 10d a sound quotation passes every check | 0.96 s |
| PASS | test 10e a missing pdf is caught | 0.81 s |
| PASS | test 10f a quotation with no approval evidence is refused | 0.71 s |
| PASS | test 11 retry exhaustion escalates and records the count | 1.19 s |
| PASS | test 12 a spent time budget stops the run | 1.17 s |
| PASS | test 12b the total time budget is separate from the per run one | 0.56 s |
| PASS | test a failed request keeps everything it was given | 0.63 s |
| PASS | test an escalated request can be resubmitted after a fix | 1.32 s |

### Manager approvals

`tests/test_approvals.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the task appears in the queue | 1.20 s |
| PASS | test the decision screen bundles the full context | 1.18 s |
| PASS | test an employee may watch but not decide | 1.19 s |
| PASS | test a customer cannot see the queue | 0.58 s |
| PASS | test approval issues the quotation | 1.28 s |
| PASS | test approval with an override reprices the quotation | 1.29 s |
| PASS | test an override within policy clears the exception | 1.29 s |
| PASS | test an override beyond policy is refused | 1.19 s |
| PASS | test an override cannot accompany a rejection | 1.18 s |
| PASS | test approval is recorded as its own execution | 1.30 s |
| PASS | test rejection closes the request | 1.19 s |
| PASS | test rejection requires a comment | 1.18 s |
| PASS | test blank comment does not satisfy the requirement | 1.16 s |
| PASS | test requesting modification returns the request to the customer | 1.36 s |
| PASS | test resubmission supersedes the old approval task | 1.26 s |
| PASS | test a resolved approval cannot be decided twice | 1.31 s |
| PASS | test approving a request gone stale is refused and reopened | 1.22 s |
| PASS | test an unknown approval id is a 404 | 0.56 s |
| PASS | test a malformed approval id is rejected | 0.57 s |
| PASS | test the manager is notified when a task is raised | 1.16 s |
| PASS | test the customer is notified of the decision | 1.29 s |
| PASS | test notifications can be marked read | 1.17 s |
| PASS | test a user cannot mark another users notification read | 1.16 s |

### Pricing engine (pure arithmetic)

`tests/test_pricing_engine.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test line without discount or tax | 0.03 s |
| PASS | test discount then tax order | 0.03 s |
| PASS | test amounts are quantised to two places | 0.03 s |
| PASS | test half up rounding not bankers rounding | 0.03 s |
| PASS | test float input does not leak binary noise | 0.02 s |
| PASS | test full discount leaves nothing payable | 0.03 s |
| PASS | test invalid inputs are rejected[kwargs0] | 0.02 s |
| PASS | test invalid inputs are rejected[kwargs1] | 0.03 s |
| PASS | test invalid inputs are rejected[kwargs2] | 0.03 s |
| PASS | test invalid inputs are rejected[kwargs3] | 0.03 s |
| PASS | test invalid inputs are rejected[kwargs4] | 0.03 s |
| PASS | test invalid inputs are rejected[kwargs5] | 0.03 s |
| PASS | test totals are the sum of rounded lines | 0.03 s |
| PASS | test effective discount percent is derived from the totals | 0.03 s |
| PASS | test empty line set totals to zero | 0.03 s |
| PASS | test product tax rate overrides the company default | 0.03 s |

### Quotations, PDF and verification

`tests/test_quotations.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the quotation snapshots both parties | 0.70 s |
| PASS | test the snapshot is frozen against later customer edits | 1.24 s |
| PASS | test validity window is set from policy | 0.69 s |
| PASS | test quotation numbers are sequential and unique | 0.84 s |
| PASS | test the pdf downloads and is a real pdf | 0.69 s |
| PASS | test downloads are counted | 0.76 s |
| PASS | test a multi line quotation renders | 0.77 s |
| PASS | test a customer cannot read another customers quotation | 1.30 s |
| PASS | test staff can read any quotation | 1.24 s |
| PASS | test only a manager can change a quotation status | 1.78 s |
| PASS | test verification needs no authentication | 0.72 s |
| PASS | test verification is case insensitive | 0.70 s |
| PASS | test an unknown code reports not found without leaking | 0.03 s |
| PASS | test tampering with a stored amount invalidates the quotation | 0.74 s |
| PASS | test tampering with a line amount is also caught | 0.71 s |
| PASS | test the hash is stable across key ordering | 0.04 s |
| PASS | test a different amount produces a different hash | 0.03 s |
| PASS | test verification codes use an unambiguous alphabet | 0.04 s |
| PASS | test expired quotations are flagged | 1.26 s |

### Request state machine and money helpers

`tests/test_state_machine.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test every status has a transition rule | 0.02 s |
| PASS | test terminal statuses allow nothing further | 0.02 s |
| PASS | test legitimate transitions are allowed[DRAFT-SUBMITTED] | 0.02 s |
| PASS | test legitimate transitions are allowed[SUBMITTED-UNDER VALIDATION] | 0.02 s |
| PASS | test legitimate transitions are allowed[UNDER VALIDATION-PRICED] | 0.03 s |
| PASS | test legitimate transitions are allowed[UNDER VALIDATION-VALIDATION FAILED] | 0.03 s |
| PASS | test legitimate transitions are allowed[PRICED-PENDING APPROVAL] | 0.02 s |
| PASS | test legitimate transitions are allowed[PRICED-APPROVED] | 0.02 s |
| PASS | test legitimate transitions are allowed[APPROVED-COMPLETED] | 0.02 s |
| PASS | test legitimate transitions are allowed[APPROVED-ESCALATED] | 0.02 s |
| PASS | test legitimate transitions are allowed[ESCALATED-SUBMITTED] | 0.02 s |
| PASS | test legitimate transitions are allowed[PENDING APPROVAL-APPROVED] | 0.02 s |
| PASS | test legitimate transitions are allowed[PENDING APPROVAL-REJECTED] | 0.02 s |
| PASS | test legitimate transitions are allowed[PENDING APPROVAL-MODIFICATION REQUESTED] | 0.02 s |
| PASS | test legitimate transitions are allowed[MODIFICATION REQUESTED-SUBMITTED] | 0.02 s |
| PASS | test legitimate transitions are allowed[VALIDATION FAILED-SUBMITTED] | 0.02 s |
| PASS | test illegal transitions are refused[DRAFT-APPROVED] | 0.02 s |
| PASS | test illegal transitions are refused[SUBMITTED-APPROVED] | 0.02 s |
| PASS | test illegal transitions are refused[COMPLETED-SUBMITTED] | 0.02 s |
| PASS | test illegal transitions are refused[APPROVED-SUBMITTED] | 0.02 s |
| PASS | test illegal transitions are refused[REJECTED-APPROVED] | 0.02 s |
| PASS | test illegal transitions are refused[CANCELLED-SUBMITTED] | 0.02 s |
| PASS | test illegal transitions are refused[PRICED-DRAFT] | 0.02 s |
| PASS | test illegal transitions are refused[COMPLETED-CANCELLED] | 0.02 s |
| PASS | test illegal transitions are refused[DRAFT-DRAFT] | 0.02 s |
| PASS | test the refusal names what would have been allowed | 0.02 s |
| PASS | test a transition accepts plain strings | 0.02 s |
| PASS | test every non terminal status can reach a terminal one | 0.02 s |
| PASS | test a valid object id round trips | 0.02 s |
| PASS | test a bad identifier raises a 422 error[] | 0.02 s |
| PASS | test a bad identifier raises a 422 error[nope] | 0.02 s |
| PASS | test a bad identifier raises a 422 error[12345] | 0.02 s |
| PASS | test a bad identifier raises a 422 error[None] | 0.02 s |
| PASS | test a bad identifier raises a 422 error[zzzzzzzzzzzzzzzzzzzzzzzz] | 0.02 s |
| PASS | test money quantises and rounds half up | 0.02 s |
| PASS | test rate quantises to two places | 0.02 s |
| PASS | test percent of is exact | 0.02 s |
| PASS | test decimals survive a round trip through bson | 0.02 s |
| PASS | test jsonable converts nested decimals to floats | 0.02 s |

### Security (auth, RBAC, passwords, downloads, config)

`tests/test_security.py`

**TestApprovalRestrictions**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test only a manager may decide | 1.23 s |
| PASS | test a customer cannot approve their own request | 0.63 s |
| PASS | test an override beyond policy is refused | 1.16 s |
| PASS | test a decided task cannot be decided again | 1.29 s |
| PASS | test a quotation cannot be issued without an approval | 0.65 s |

**TestAuthentication**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a protected endpoint refuses an anonymous caller | 0.03 s |
| PASS | test the challenge header is sent | 0.03 s |
| PASS | test a malformed token is refused[] | 0.03 s |
| PASS | test a malformed token is refused[not-a-jwt] | 0.03 s |
| PASS | test a malformed token is refused[Bearer.Bearer.Bearer] | 0.03 s |
| PASS | test a malformed token is refused[eyJhbGciOiJIUzI1NiJ9.e30.invalid-signature] | 0.03 s |
| PASS | test a token signed with the wrong key is refused | 0.56 s |
| PASS | test an expired token is refused | 0.57 s |
| PASS | test a refresh token cannot be used as an access token | 0.56 s |
| PASS | test a token for a deleted account is refused | 0.57 s |
| PASS | test suspension takes effect on an existing token | 0.57 s |
| PASS | test the login error does not reveal whether an account exists | 1.09 s |

**TestAuthorisation**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/customers] | 0.56 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/products] | 0.59 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/approvals] | 0.60 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/approvals/pending-count] | 0.57 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/audit-logs] | 0.57 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/analytics/overview] | 0.57 s |
| PASS | test a customer is refused staff endpoints[GET-/api/v1/analytics/dashboard] | 0.56 s |
| PASS | test a customer is refused staff endpoints[POST-/api/v1/quotations/expire-due] | 0.56 s |
| PASS | test an employee is refused manager endpoints[GET-/api/v1/audit-logs] | 0.57 s |
| PASS | test an employee is refused manager endpoints[GET-/api/v1/analytics/dashboard] | 0.56 s |
| PASS | test an employee is refused manager endpoints[GET-/api/v1/analytics/exceptions] | 0.55 s |
| PASS | test an employee is refused manager endpoints[GET-/api/v1/analytics/customers/top] | 0.56 s |
| PASS | test an employee is refused manager endpoints[GET-/api/v1/analytics/revenue/trend] | 0.57 s |
| PASS | test an employee cannot change the rule book | 0.56 s |
| PASS | test an employee cannot block a customer | 1.09 s |
| PASS | test an employee cannot discontinue a product | 0.56 s |
| PASS | test a customer cannot create a staff account | 0.58 s |
| PASS | test the staff route will not mint a customer login | 0.59 s |
| PASS | test a customer cannot reprocess a workflow | 0.59 s |
| PASS | test a customer cannot write internal notes | 0.62 s |

**TestConfiguration**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the secrets are read from the environment | 0.04 s |
| PASS | test no env file is committed | 0.03 s |
| PASS | test an env template carries no real secrets[backend/.env.example-change-me] | 0.03 s |
| PASS | test an env template carries no real secrets[.env.docker.example-replace-me] | 0.03 s |
| PASS | test the compose file demands the secrets be set | 0.03 s |
| PASS | test the production image does not run as root | 0.03 s |
| PASS | test the production image disables debug | 0.03 s |
| PASS | test no secret is hard coded in the application | 0.06 s |
| PASS | test the verification digest depends on the secret | 0.03 s |
| PASS | test the audit trail has no write endpoint | 0.03 s |

**TestCustomerIsolation**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a customer cannot read another customers request | 1.23 s |
| PASS | test a customers list is scoped to their own records | 1.25 s |
| PASS | test a customer cannot read another customers quotation | 1.23 s |
| PASS | test a customer cannot submit on behalf of another | 0.69 s |
| PASS | test a customer cannot read another users notification | 1.18 s |

**TestEndpointProtection**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test every other route requires authentication | 0.03 s |
| PASS | test the public verification endpoint needs no token | 0.03 s |
| PASS | test the health endpoint needs no token | 0.03 s |

**TestFileDownloads**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a pdf cannot be downloaded anonymously | 0.69 s |
| PASS | test a pdf cannot be downloaded by another customer | 1.27 s |
| PASS | test the owner can download their pdf | 0.72 s |
| PASS | test the download filename is the quotation number | 0.69 s |
| PASS | test a download is audited | 1.26 s |

**TestPasswordSecurity**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a password is stored as a bcrypt hash | 0.31 s |
| PASS | test the password never appears in a response | 0.32 s |
| PASS | test hashing is salted | 1.07 s |
| PASS | test a wrong password does not verify | 1.06 s |
| PASS | test a malformed stored hash fails closed | 0.02 s |
| PASS | test a short password is refused at registration | 0.04 s |
| PASS | test changing a password requires the current one | 0.83 s |

### Workflow boundaries (retries, gate, no-op, escalation, budget)

`tests/test_workflow_boundaries.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test decimal import is used | 0.04 s |

**TestBudgetLimit**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the attempt ceiling stops reprocessing | 1.78 s |
| PASS | test attempts are counted even when a run fails | 0.60 s |
| PASS | test elapsed time accumulates across attempts | 0.70 s |
| PASS | test the line ceiling is enforced | 1.18 s |
| PASS | test the quantity ceiling is enforced | 1.18 s |
| PASS | test a spent duration budget raises | 0.03 s |
| PASS | test a spent total duration budget raises | 0.03 s |
| PASS | test the attempt ceiling is checked before work starts | 0.03 s |
| PASS | test the budget blocks a step once spent | 0.03 s |
| PASS | test every limit is configurable through the api | 0.64 s |
| PASS | test an invalid limit is rejected | 0.65 s |
| PASS | test backoff grows with each retry | 0.03 s |

**TestEscalationCondition**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test missing customer information escalates | 0.62 s |
| PASS | test product unavailability escalates when backorders are off | 1.24 s |
| PASS | test a discount exception escalates to a manager | 0.63 s |
| PASS | test manager rejection settles the request | 1.19 s |
| PASS | test a repeated processing failure escalates | 0.97 s |
| PASS | test a verification mismatch escalates | 1.19 s |
| PASS | test an escalated request notifies the manager | 1.56 s |
| PASS | test escalation is audited with the reason | 1.58 s |

**TestMaximumIterations**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a transient failure is retried then succeeds | 0.88 s |
| PASS | test retries stop at the configured maximum | 1.58 s |
| PASS | test the retry limit is configurable | 1.26 s |
| PASS | test a permanent failure is never retried | 0.62 s |
| PASS | test a validation verdict is not treated as a fault | 0.61 s |
| PASS | test failures are classified[error0-TRANSIENT] | 0.03 s |
| PASS | test failures are classified[error1-TRANSIENT] | 0.03 s |
| PASS | test failures are classified[error2-TRANSIENT] | 0.03 s |
| PASS | test failures are classified[error3-PERMANENT] | 0.02 s |
| PASS | test failures are classified[error4-PERMANENT] | 0.02 s |
| PASS | test the budget retries then re raises | 0.03 s |

**TestNoOpCondition**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test rerunning a completed request is a no op | 1.24 s |
| PASS | test every step is recorded as skipped | 0.70 s |
| PASS | test the no op is audited | 1.27 s |
| PASS | test repeated triggers accumulate the count | 0.74 s |
| PASS | test a rejected request is also settled | 1.21 s |

**TestSuccessGate**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test completion requires all six conditions | 0.69 s |
| PASS | test the gate is allow on proof not allow by default | 0.03 s |
| PASS | test any single unmet condition blocks completion[input validation passed] | 0.03 s |
| PASS | test any single unmet condition blocks completion[product verification passed] | 0.02 s |
| PASS | test any single unmet condition blocks completion[pricing validation passed] | 0.03 s |
| PASS | test any single unmet condition blocks completion[approval recorded] | 0.03 s |
| PASS | test any single unmet condition blocks completion[document generated] | 0.02 s |
| PASS | test any single unmet condition blocks completion[independent verification passed] | 0.03 s |
| PASS | test a queued request does not reach the gate | 0.62 s |
| PASS | test verification failure blocks completion | 0.71 s |

### Workflow pipeline

`tests/test_workflow.py`

| Result | Test | Time |
| --- | --- | --- |
| PASS | test in policy request is auto approved and quoted | 0.68 s |
| PASS | test discount within the tier is auto approved | 0.71 s |
| PASS | test a draft is not processed until submitted | 0.70 s |
| PASS | test discount above the tier goes to a manager | 0.62 s |
| PASS | test an approval task is created with the sla and snapshot | 0.63 s |
| PASS | test order value threshold forces review | 1.21 s |
| PASS | test threshold of zero disables the value check | 1.25 s |
| PASS | test credit limit breach forces review | 0.62 s |
| PASS | test stock shortfall forces review but still quotes | 0.68 s |
| PASS | test reserved stock is not available to quote | 0.64 s |
| PASS | test backorder can be forbidden by policy | 1.20 s |
| PASS | test several exceptions are all reported | 1.21 s |
| PASS | test a discontinued product fails validation | 0.62 s |
| PASS | test a blocked customer fails validation | 0.57 s |
| PASS | test a customer put on hold mid flight fails validation | 0.62 s |
| PASS | test a discount beyond the absolute maximum fails validation | 0.63 s |
| PASS | test a discount below cost fails validation | 0.62 s |
| PASS | test an unknown product is rejected at creation | 0.59 s |
| PASS | test a duplicate product line is rejected by the schema | 0.61 s |
| PASS | test zero quantity is rejected by the schema | 0.65 s |
| PASS | test an empty item list is rejected by the schema | 0.64 s |
| PASS | test the execution records every step in order | 0.73 s |
| PASS | test steps after a failure are recorded as skipped | 0.66 s |
| PASS | test the pricing step records the figures it produced | 0.71 s |
| PASS | test the discount step records the rule trace | 0.75 s |
| PASS | test identical submissions produce identical decisions | 0.80 s |
| PASS | test status history records the whole journey | 0.69 s |
| PASS | test a failed request can be fixed and resubmitted | 0.72 s |
| PASS | test an approved request cannot be edited or resubmitted | 0.69 s |
| PASS | test editing a draft clears any earlier pricing | 0.63 s |
| PASS | test a request can be cancelled | 0.65 s |
| PASS | test an approved request cannot be cancelled | 0.69 s |
| PASS | test pricing uses the catalogue price at submission time | 1.23 s |
| PASS | test a customer cannot read another customers request | 1.26 s |
| PASS | test staff can read any request | 1.26 s |
| PASS | test staff must name a customer when raising a request | 0.57 s |
| PASS | test staff can raise a request on behalf of a customer | 0.71 s |
| PASS | test a customer cannot submit for someone else | 0.69 s |
| PASS | test a product tax override is applied | 0.70 s |
| PASS | test a product discount cap is applied | 0.65 s |
| PASS | test reprocess clears a request once the cause is fixed | 1.25 s |
| PASS | test reprocess records a repeat failure instead of erroring | 1.21 s |
| PASS | test reprocess leaves a second execution trace | 1.32 s |
| PASS | test a customer cannot reprocess | 0.64 s |
| PASS | test an approved request cannot be reprocessed | 1.32 s |
| PASS | test a pending approval cannot be reprocessed | 1.18 s |

### Master-data authorisation (manager approval)

`tests/test_master_data_requests.py`

**TestApproval**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test approving creates the customer | 1.16 s |
| PASS | test the approved customer appears in the customer list | 1.15 s |
| PASS | test approving creates the product | 1.12 s |
| PASS | test the decision records who authorised it | 1.13 s |
| PASS | test the audit trail names the proposer and the authoriser | 1.16 s |
| PASS | test the created customer is audited against the manager | 1.18 s |
| PASS | test the employee is told the outcome | 1.15 s |
| PASS | test managers are told a request is waiting | 1.12 s |
| PASS | test approving frees the slot for another proposal | 1.13 s |

**TestDecisionAuthority**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test an employee cannot approve anything | 0.59 s |
| PASS | test an employee cannot approve their own request | 0.59 s |
| PASS | test a customer cannot decide | 1.12 s |
| PASS | test a decision cannot be taken twice | 1.12 s |
| PASS | test an approved request cannot be approved again | 1.15 s |
| PASS | test an unknown request is a 404 | 0.57 s |
| PASS | test a malformed id is a 422 | 0.57 s |

**TestDirectCreationIsManagerOnly**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test an employee cannot create a customer | 0.57 s |
| PASS | test an employee cannot create a product | 0.58 s |
| PASS | test the refusal writes nothing | 0.58 s |
| PASS | test a manager can still create a customer directly | 0.59 s |
| PASS | test a customer cannot use the approval queue | 0.58 s |
| PASS | test an employee may still edit an existing customer | 1.11 s |

**TestProtection**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test every route requires a token | 0.04 s |

**TestQueue**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test a manager sees the whole queue | 1.17 s |
| PASS | test the pending count drives the managers badge | 1.13 s |
| PASS | test an employee sees only their own requests | 1.12 s |
| PASS | test an employee cannot read another persons request | 1.11 s |
| PASS | test the queue can be filtered by entity type | 1.15 s |
| PASS | test the queue can be filtered by status | 1.19 s |

**TestRefusal**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test refusing creates nothing | 1.15 s |
| PASS | test a refusal requires a reason | 1.14 s |
| PASS | test a blank reason does not count | 1.13 s |
| PASS | test the submitted values survive a refusal | 1.14 s |
| PASS | test a refused record can be proposed again | 1.15 s |

**TestSubmission**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test an employee can submit a customer | 0.58 s |
| PASS | test submitting does not touch the customers collection | 0.57 s |
| PASS | test the submitted values are preserved verbatim | 0.58 s |
| PASS | test an employee can submit a product | 0.58 s |
| PASS | test an invalid payload is refused at submission | 0.57 s |
| PASS | test a manager may also submit rather than create | 0.58 s |
| PASS | test a customer that already exists is refused immediately | 1.11 s |
| PASS | test a product sku that already exists is refused immediately | 0.57 s |
| PASS | test the same record cannot be queued twice | 0.58 s |
| PASS | test a second employee cannot queue the same record | 1.12 s |

**TestWithdrawal**

| Result | Test | Time |
| --- | --- | --- |
| PASS | test the requester can withdraw their own | 0.59 s |
| PASS | test somebody else cannot withdraw it | 1.12 s |
| PASS | test a withdrawn request cannot then be approved | 1.13 s |
| PASS | test withdrawing frees the record to be proposed again | 0.62 s |
