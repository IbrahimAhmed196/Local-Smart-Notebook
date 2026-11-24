<!-- image -->

CSE336s - Software Design Patterns

## Lab 07

## Learning Outcomes

- Select suitable design patterns from requirements and justify the choices.
- Identify class roles and relationships when seven patterns cooperate in one system.
- Complete a partially implemented Java console application and verify its behavior.
- Design and implement a small extension without being told which pattern to apply.

## Problem 1 | Understand the Application and Its Design

A university food-delivery application reads its menu from CSV. A customer selects one meal, optionally adds extras, chooses a delivery method and places an order. The system assigns a courier, notifies the kitchen and customer, and saves the order in CSV. One meal per order; no database, GUI or external libraries are required.

## Part A - Run and Inspect the Starter

1. Extract CampusFoodDelivery\_Lab07\_Starter; open it as a Java project or use the command line from the project root.
2. Compile the project, then run PatternChecks. Expect 0 passed / 7 failed before implementing the TODOs.
3. Inspect the src/ directory and data/menu.csv. Run Main and observe where the current workflow stops.
4. Do not rewrite the provided CSV helper; focus on class responsibilities and pattern collaboration.

## Part B - Match Requirements to Patterns

Before coding, fill in the pattern, actual class/interface roles, and a one-sentence justification for each requirement.

| Change request / requirement                                          | Pattern   | Class roles / justification   |
|-----------------------------------------------------------------------|-----------|-------------------------------|
| More meal types without constructing them directly in the Controller. |           |                               |
| Stackable meal extras at runtime.                                     |           |                               |
| Different delivery-fee calculations.                                  |           |                               |
| One shared pool of available couriers.                                |           |                               |
| Multiple listeners react when order status changes.                   |           |                               |
| One high-level operation for order placement.                         |           |                               |
| Separate domain state, interaction and console display.               |           |                               |

## Problem 2 | Identify the Architecture and UML Relationships

Inspect the starter class declarations and sketch a small UML diagram. Do not attempt to draw every utility or test class during the lab.

1. Show Meal with Burger, Pizza and Sushi; MealDecorator with ExtraCheese and ComboSide.
2. Show DeliveryStrategy with StandardDelivery and ExpressDelivery; Order with OrderObserver and two concrete observers.

3. Show OrderController, ConsoleView, OrderPlacementFacade and FleetManager.
4. Label interface implementation, inheritance, association, composition/wrapping and dependency correctly.

Question: Which classes should remain unchanged when another meal extra is introduced? Explain using the Open/Closed Principle.

## Problem 3 | Complete the Seven Patterns

Complete the TODOs in the supplied starter. After each group of changes, recompile and run PatternChecks. Keep each responsibility in its intended class.

| TODO / pattern      | Implementation checkpoint                                                                               |
|---------------------|---------------------------------------------------------------------------------------------------------|
| 1 - Simple Factory  | MealFactory creates Burger, Pizza or Sushi according to MenuItemData.type; reject unsupported types.    |
| 2 - Decorator       | ComboSide wraps a Meal; add " + Combo Side" to its description and 25 EGP to its price.                 |
| 3 - Strategy        | ExpressDelivery reports "Express Delivery" and calculates a 30 EGP fee.                                 |
| 4-5 - Singleton     | FleetManager provides one instance; assignCourier removes a courier from the available pool.            |
| 6 - Observer        | Order notifies registered observers on status changes; CustomerNotifier prints the order ID and status. |
| 7 - Facade          | Calculate the strategy fee, assign courier, update Order, mark PLACED and append the CSV row.           |
| 8 - MVC integration | OrderController registers both observers, invokes the Facade once and displays the completed order.     |

## Problem 4 | Verify the Complete Application

## Part A - Run the Checks

From the project root, run the following in order:

run PatternChecks

run IntegrationChecks

run Main

Expected: PatternChecks = 7 passed / 0 failed; IntegrationChecks = PASS.

## Part B - Trace One Order End to End

Example: Classic Burger (80 EGP) + Extra Cheese (15) + Combo Side (25) + Express Delivery (30) = 150 EGP.

1. Confirm that BOTH KitchenDisplay and CustomerNotifier receive the PLACED notification.
2. Confirm the assigned courier, total amount and order status in the View.
3. Confirm that the order appears as a new row in data/orders.csv.
4. Explain why passing seven isolated pattern tests does not guarantee that MVC and the complete workflow are correctly connected.

## Problem 5 | Independent Extension: Insulated Packaging

New requirement: Customers may add Insulated Packaging for +12 EGP to ANY meal, including meals with other extras. The requirement does not specify a pattern.

## Part A - Design Before Coding

1. Choose a pattern and justify why it fits the requirement better than the alternatives studied.
2. Name the new class, its parent/interface, and the reference it holds. Update your UML sketch.
3. Identify the minimum existing code that must change to offer the option in the console workflow.

## Part B - Implement and Test

1. Implement the new behavior and add a yes/no option in the user interaction.
2. Verify Burger + Packaging + Express = 80 + 12 + 30 = 122 EGP.
3. Verify packaging can be combined with the existing extras and does not alter their calculations.
4. Complete unfinished extension work after class; this is the independent portion of the lab.