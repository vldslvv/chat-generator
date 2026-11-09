# Design of agentic approach

The core idea is to transform the traditional agent instructions into program-like instructions in plain English, organizing the similarly to programming module rather than a set of guides.

This means that every block of ideas should be expressed once, referenced where they are needed. The agent will pick up the reference in the document while scanning for its root instructions.

The models are getting smarter and I expect them to require less and less steering, this means that in the future we may remove more instructions than we add, focusing on specifications and verifications instead.

The core workflow is expressed at <put WORKFLOW.md path here>

Rest of the documents are derived from it, enriching the context and instructions.

To maintain alignment between WORKFLOW.md and the rest of the documents, an eval is implemented that uses LLM as a judge approach. To use it, run <put eval here>.

## Specifications

Specifications are implemented as a set of tasks and DAG-like execution section.

<links to examples here>

Each task is a self-contained unit of work.

## Implementation flows

The main agent is supervisor -- it reads the task order and spawns agents that implement individual tasks.

There are two possible flows: direct flow and plan-review flow. Direct flow uses the single agent session to implement and plan-review has two agents, one implements, another reviews using fresh context, iterating until acceptance is reached.

The supervisor support implementation from scratch, reconciliation against changed requirements, and new task flow against existing project.

# Chat design

The application is designed around contracts and behaviours.

There are few contracts:

<contract links at spec_chat here>>

There are two conceptual entities: api and chat

Api is here: <link>

Chat has a generic behaviour: <link>, while Python and 
