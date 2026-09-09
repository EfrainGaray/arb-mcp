Feature: The merge gate
  Only deterministic rules decide whether a design may merge. Every rule below
  is one an architecture review board can read without the code: same model
  in, same verdict out, no clock, no network, no model weights.

  Background:
    Given the C4 spec

  Scenario: A container that holds components but carries no documentation is blocked
    Given a software system "Billing" with a container "API" that holds a component "Auth"
    And a decision "ADR-1" that affects "Billing" and "API"
    And every element is described and every relation names its technology
    When the design is validated
    Then it may not merge
    And the findings include ERROR "model.container.documentation"

  Scenario: The same design validated twice yields the same findings
    Given a software system "Billing" with a container "API" that holds a component "Auth"
    When the design is validated twice
    Then both verdicts are identical

  Scenario: A relation to an element that does not exist is blocked, never drawn
    Given a person "User"
    And a relation from "User" to "Ghost"
    When the design is validated
    Then the findings include ERROR "model.relation.endpoint"

  Scenario: A type the spec does not declare cannot pass the gate
    Given an element "X" of type "microservice"
    When the design is validated
    Then it may not merge
    And the findings include ERROR "model.type.undeclared"

  Scenario: A missing description is a warning, not a block
    Given a person "User"
    And a software system "Billing"
    And a relation from "User" to "Billing" over "HTTPS"
    And a decision "ADR-1" that affects "Billing"
    When the design is validated
    Then it may merge
    And the findings include WARNING "model.person.description"

  Scenario Outline: The scope must be declared with a closed value
    Given a person "User" described as "someone"
    And the model scope is "<scope>"
    When the design is validated
    Then the verdict on "model.scope" is <verdict>

    Examples:
      | scope     | verdict  |
      | system    | absent   |
      | landscape | absent   |
      | undefined | ERROR    |
