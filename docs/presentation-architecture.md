# ARC-01: Presentation architecture

Status: Design approved; contracts adopted incrementally in follow-up tasks.

Source: ARC-01_Target_module_structure_and_interfaces.pdf,
approved by the team on 26 October 2026.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| api/presentations.py | HTTP routes and ownership checks |
| services/presentation_service.py | Validate requests, create/read/edit/delete presentations, submit jobs |
| presentations/runner.py | Job lifecycle, status, progress, failures and startup recovery |
| presentations/generator.py | Compose implementations and coordinate context, outline and slide generation |
| presentations/outline.py | Outline generation, validation and repair |
| presentations/rendering.py | Map options and artifact paths to PPTX rendering |
| presentations/context/ | Context schemas, document readers and interchangeable providers |
| database/repositories/presentation_repo.py | Shared database helpers |
| agents/slide_content_agent.py | Slide writing and content validation |
| llm/ | JSON client, readiness, model errors and prompts |
| tools/ | Spreadsheet calculations and PPTX rendering |

These are target locations. ARC-01 adds declarations only.

## Request flow

1. The service validates the request, inserts PENDING and submits the job.
2. The runner starts the job and records status and progress.
3. The runner calls generator.get_generator() through the module.
4. The generator coordinates readiness, context, outline and slide writing.
5. The runner calls the shared rendering wrapper and stores the result.
6. The runner marks the job completed or failed.

Manual deck editing also uses the shared rendering wrapper.

## Dependency rules

- Keep AI logic out of the API and presentation service.
- Construct concrete clients and providers at the composition point.
- Pass clients to outline, context and slide generation.
- Generator, outline and context code must not open sessions or commit.
- Existing ORM inputs are transitional read-only inputs; avoid lazy database
  reads inside the generation pipeline.
- Put shared database helpers in the repository, avoiding service/runner
  imports of each other.
- Call generator.get_generator() through its module so tests can replace it.
- Keep GenerationCancelled separate from LlmError.
- Context selection receives context explicitly rather than relying on
  hidden provider state.

## Contracts

LlmClient defines readiness and typed JSON generation.

ContextProvider builds context and selects evidence using
for_slide(context, item).

OutlineGenerator and SlideWriter describe callable pipeline steps.

DeckGenerator defines the boundary between runner and generation.

Progress remains Callable[[str], None] until JOB-02.

## Migration

- ARC-01: add declarations; preserve production behavior and test overrides.
- ARC-02: extract outline generation and its prompt.
- LLM-01 / ARC-03: adopt shared model errors and readiness; update the JSON
  client and scripted fake together, preserving chat behavior.
- ARC-04: extract the generator, move its test override and remove default
  concrete-client creation from the slide writer.
- ARC-05: extract the runner and shared database helpers.
- CTX-01: define the complete context schemas.
- LLM-03 / JOB tasks: implement cancellation before passing cancel_event.

The target LlmClient includes capabilities that current clients do not yet
implement. Declaring the Protocol does not implement those capabilities.

Update contracts, implementations, callers and fakes together whenever
an interface changes. Preserve behavioral assertions during extraction;
update import paths, patch targets and readiness expectations as needed.

## Completion

ARC-01 is complete when the approved declarations are integrated,
the existing QA suite passes and the changes are committed.