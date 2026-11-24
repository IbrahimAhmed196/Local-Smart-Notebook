## CSE336s: Software Design Patterns

Lecture 6: MVC and Façade design patterns

## Model-View-Controller (MVC) Design Pattern

## Learning resources

- Chapter 12 (Compound Patterns), Head First Design Patterns, 2nd edition, Freeman &amp; Robson -MVC begins p. 523

O'REILLY

## Head First

## Design Patterns

Building Extensible &amp; Maintainable Object-Oriented Software

Eric Freeman &amp; Elisabeth Robson with Kathy Sierra &amp; Bert Bates

A Brain-Friendly Guide Second Edition

<!-- image -->

<!-- image -->

## Another design problem: Employee Manager

Employees are stored in SQL. First, we build a working program that finds one employee by ID.

## EMPLOYEE TABLE · DATABASE

|   ID | Name            | Address     |
|------|-----------------|-------------|
|    1 | Ahmed Hesham    | Cairo       |
|    2 | Mohamed Hussein | Iraq        |
|    3 | Hania           | Egypt       |
|   16 | Hussein         | Madint Nasr |

## USER ACTIONS

- Find employee by ID
- Display employee details

Question: could one Java class retrieve and display employee information?

## Before MVC -one class does everything

EmployeeApplication.java combines input requests, JDBC retrieval, and console presentation.

```
public static void showEmployee(int id) throws Exception { String sql = "SELECT id, name, address " + "FROM employees WHERE id = ?"; try (Connection c = DriverManager.getConnection( "jdbc:h2:./data/employeesdb", "sa", ""); PreparedStatement st = c.prepareStatement(sql)) { st.setInt(1, id); ResultSet rs = st.executeQuery(); if (rs.next()) { System.out.println("ID: " + rs.getInt("id")); System.out.println("Name: " + rs.getString("name")); System.out.println("Address: " + rs.getString("address")); } else { System.out.println("Employee " + id + " not found"); } } }
```

## USER REQUESTS

showEmployee(2);

showEmployee(999);

One method owns SQL and console display.

<!-- image -->

## What goes wrong when responsibilities mix?

Our first version works, but EmployeeApplication mixes different responsibilities.

01

## SQL access

Open connection Execute SELECT Convert rows to objects

02

## Presentation

Display employee details Print not-found message Choose console format

03

## Interaction

Main invokes requests showEmployee(id) handles them

What if we replace the console with JavaFX? Which parts should change?

<!-- image -->

## MVC separates three responsibilities

Model · View · Controller: organize application state, presentation and input handling.

MODEL

## EmployeeModel

Gets Employee data from SQL; validates IDs. No console output.

VIEW

## EmployeeView

Formats and displays Employee

objects. No database access.

CONTROLLER

## EmployeeController

Receives requests; asks Model, then View.

## Design principle: separation of concerns.

<!-- image -->

## Where does the employee data come from?

<!-- image -->

## The Model is not the database.

To use a file later, we would replace the data-reading code inside EmployeeModel. The Controller and View could remain unchanged.

<!-- image -->

## Representing an Employee as a Java Object

An Employee object represents one record returned by EmployeeModel.

```
public class Employee { private int id; private String name; private String address;
```

```
// constructor and getters ... }
```

SQL row → Employee object → Controller → View Example object id: 2

name: Mohamed Hussein

address: Iraq

<!-- image -->

## EmployeeModel retrieves data using JDBC

The SQL query is part of EmployeeModel in this introductory implementation.

```
String sql = "SELECT id, name, address " + "FROM employees WHERE id = ?"; try (Connection connection = DriverManager.getConnection( "jdbc:h2:./data/employeesdb", "sa", ""); PreparedStatement statement = connection.prepareStatement(sql)) { statement.setInt(1, id); ResultSet result = statement.executeQuery(); if (result.next()) { return new Employee(result.getInt("id"), result.getString("name"), result.getString("address")); } } return null;
```

## DATABASE → JAVA

1 Connect to SQL

2 Execute SELECT

- 3 Return Employee

<!-- image -->

## The View formats the result

Today we use the console. A JavaFX screen could present exactly the same Employee.

```
public void showEmployee(Employee e) { System.out.println("ID: " + e.getId()); System.out.println("Name: " + e.getName());
```

```
System.out.println("Address: " + e.getAddress()); }
```

EmployeeView does not know how SQL connections or queries work.

CONSOLE OUTPUT

ID: 2

Name: Mohamed

Hussein

Address: Iraq

<!-- image -->

## The Controller coordinates the request

A user requests employee 2. The Controller asks the Model, then calls the View.

```
public void showEmployee(int id) throws Exception { Employee employee = model.getEmployee(id); if (employee != null) { view.showEmployee(employee); } else { }
```

```
view.showMessage("Employee " + id + " not found"); }
```

The Controller does not contain SQL or formatting instructions.

CONTROLLER

Receives an ID

Requests employee

Chooses output

<!-- image -->

## Trace one employee request, from call to console output

The Controller coordinates. The Model executes SQL and creates an Employee object.

## REQUEST

<!-- image -->

## MVC -Java class diagram

<!-- image -->

Main creates the objects · Model queries SQL · Controller coordinates · View displays

<!-- image -->

## Could we replace the console with JavaFX?

## Employee Details

Employee ID

2

Find Employee

Mohamed Hussein -Iraq

## What stays the same?

- Employee entity and Model logic
- SQL data source

## What changes?

- Replace console View with JavaFX
- Connect button to Controller

<!-- image -->

## Quick check: who should do this?

| Run SELECT and create Employee from SQL   | ?   |
|-------------------------------------------|-----|
| Check that an employee ID is positive     | ?   |
| Print the employee name and address       | ?   |
| Handle a Find Employee request            | ?   |

Where should SQL live in this simplified implementation?

<!-- image -->

## Quick check: model answers

| Run SELECT and create Employee from SQL   | Model (JDBC code)   |
|-------------------------------------------|---------------------|
| Check that an employee ID is positive     | Model               |
| Print the employee name and address       | View                |
| Handle a Find Employee request            | Controller          |

Answer: EmployeeModel retrieves SQL data directly (teaching simplification).

<!-- image -->

## MVC Pattern Card

Responsibilities · participants · example · principles

## PROBLEM

One class mixes SQL retrieval, user requests and console presentation.

## CORE IDEA

Extract Model, View, and Controller from EmployeeApplication.

## IN THIS LECTURE

Before: EmployeeApplication

After: EmployeeModel + View + Controller

## PARTICIPANTS

Employee (domain data) EmployeeModel · EmployeeView EmployeeController

## KEY PRINCIPLES

Separate concerns · reduce coupling · change independently

MVC separates responsibilities; database access can remain in Model for this small example.

## Façade Design Pattern

## Learning resources

- Chapter 7 Head First Design Patterns, 2 nd edition, Freeman &amp; Robson

O'REILLY®

## Head First

## Design Patterns

Building Extensible &amp; Maintainable Object-Oriented Software

Eric Freeman &amp; Elisabeth Robson with Kathy Sierra &amp; Bert Bates

A Brain-Friendly Guide Second Edition

<!-- image -->

## Home Theatre

<!-- image -->

## Watching a movie (the hard way)

- Turn on the popcorn popper
- Start the popper popping
- Dim the lights
- ④ Put the screen down
- Turn the projector on
- © Set the projector input to streaming player
- Put the projector on widescreen mode
- © Turn the sound amplifier on
- © Set the amplifier to streaming player input
- 1Set the amplifier to surround sound
- ① Set the amplifier volume to medium (5)
- Turn the streaming player on
- Start playing the movie

<!-- image -->

## Watching a Movie

<!-- image -->

```
Turn on the popcorn popper and start popping... popper.on() ; popper.pop() ; Dim the lights to 10%... lights.dim(10); Six different classes Put the screen down.. involved! screen.down () ; Turn on the projector and put it in projector.on() ; widescreen mode for the movie... projector.setInput(player) ; projector.wideScreenMode() ; Turn on the amp, set it to Streaming amp.on() ; player, put it in surround-sound mode, amp.setStreamingPlayer(player) ; and set the volume to 5... amp.setSurroundSound() ; amp.setVolume (5) ; Turn on the Streaming player... player.on() ; and FINALLY, play the movie! player.play(movie) ;
```

## Design Smell: The Client Knows Too Much

What is wrong with controlling the home theatre directly?

## CLIENT CODE

Turns on the popper, lights, screen, projector, amplifier and player-in the correct order.

## CHANGES RIPPLE

Changing a device or startup sequence may require editing many clients.

## How could a client simply ask: "watchMovie()"?

## The Façade!

- The Facade still leaves the subsystem accessible so it can be used directly.
- A facade not only simplifies an interface, it decouples a client from a subsystem of components.

<!-- image -->

## The Facade Changes the Client's Job

Before: sequence of low-level calls. After: one high-level request.

```
BEFORE popper.on(); popper.pop(); lights.dim(10); screen.down(); projector.on(); amp.on(); player.on(); player.play(movie);
```

## AFTER

theater.watchMovie(movie);

// Facade orchestrates // the same subsystem calls

The subsystem remains available: Facade simplifies the common workflow rather than hiding every capability.

## Constructing the Facade

```
CSE 336s - Software Design Patterns 28 public class HomeTheaterFacade Here's the composition; these Amplifier amp; aue oe unodne  lle the Tuner tuner; subsystem we are going to use. StreamingPlayer player; Projector projector; TheaterLights lights; Screen screen; PopcornPopper popper; public HomeTheaterFacade(Amplifier amp, Tuner tuner, StreamingPlayer player; The facade is passed a Projector projector, reference to each component Screen screen, of the subsystem in its TheaterLights lights, constructor. The facade PopcornPopper popper) { then assigns each to the corresponding instance variable. this.amp = amp; this.tuner = tuner; this.player = player; this.projector = projector; this.screen = screen; this.lights = lights; this.popper = popper; // other methods here We're just about to fill these in...
```

## Implementing the simplified interface

```
public void watchMovie(String movie) { System.out.println("Get ready to watch a movie..."); popper.on () ; popper.pop() ; watchMovie() follows the same sequence we had to do by hand before, but wraps lights.dim(10) ; it up in a handy method that does all screen.down () ; the work. Notice that for each task we projector.on() ; are delegating the responsibility to the projector.wideScreenMode() ; corresponding component in the subsystem. amp. on () ; amp.setStreamingPlayer (player) ; amp. setSurroundSound() ; amp. setVolume (5) ; player.on () ; player.play(movie) ;
```

## Implementing the simplified interface

And endMovie() takes care of shutting everything down for public void endMovie() { us. Again, each task is delegated to the appropriate component in the subsystem.

```
System.out.println("Shutting movie theater down...") ; popper.off() ; lights.on () ; screen.up() ; projector.off() ; amp.off () ; player.stop() ; player.off() ;
```

## Time to watch a movie (the easy way)

```
Here we're creating the components public class HomeTheaterTestDrive { right in the test drive. Normally the public static void main(String[] args) { client is given a facade; it doesn't have to construct one itself. // instantiate components here First you instantiate HomeTheaterFacade homeTheater = the Facade with all the new HomeTheaterFacade(amp, tuner, player, components in the subsystem. projector, screen, lights, popper); homeTheater.watchMovie("Raiders of the Lost Ark"); Use the simplified interface to homeTheater.endMovie () ; first start the movie up, and then shut it. down.
```

## The output

<!-- image -->

<!-- image -->

Here's the output. Get ready to watch a movie... Calling the Facade's watchMovie() does all this work for us... Amplifier setting Streaming player to Streaming Amplifier setting volume to 5 Streaming Player playing "Raiders of the Lost Ark" ...and here, we're done 7 watching the movie, so calling endMovie() turns everything off 7 Streaming Player stopped "Raiders of the Lost Ark"

```
File Edit Window Help SnakesWhy'dltHaveToBeSnakes? %java HomeTheaterTestDrive Popcorn Popper on Popcorn Popper popping popcorn! Theater Ceiling Lights dimming to 10% Theater Screen going down Projector on Projector in widescreen mode (16x9 aspect ratio) Amplifier on Player Amplifier surround sound on (5 speakers, 1 subwoofer) 5 Streaming Player on Shutting movie theater down... Popcorn Popper off Theater Ceiling Lights on Theater Screen going up Projector off Amplifier off Streaming Player off %
```

## Facade Pattern defined

The Facade Pattern provides a unified interface to a set of interfaces in a subsystem. Facade defines a higherlevel interface that makes the subsystem easier to use.

## Façade - Class Diagram

<!-- image -->

## How Do I Recognize Facade?

One entry point simplifies tasks

Calls are delegated to subsystems

Clients know fewer details Clients use high-level operations such as watchMovie().

The facade coordinates existing subsystem classes.

They need not learn every device API or call order.

Recognition clue

Look for a high-level interface that delegates a workflow to subsystem objects.

Caution: a facade does not eliminate or replace the subsystem interfaces.

## Quick Check: Facade, Strategy, or Decorator?

One-click checkout

Choose an algorithm at runtime

Add compression to a stream A service coordinates payment, stock and shipping calls.

The user selects QuickSort instead of MergeSort.

A wrapper adds behavior while retaining the same interface.

## Discuss

Which illustrates Facade, Strategy, and Decorator? Why?

## Where Else Can We See Facade?

Common operations made easier with a unified interface

Online checkout

Document publishing

Computer startup One place to coordinate payment, inventory and shipping.

One operation to format, convert, store and distribute.

A launcher coordinates configuration, logging and services.

Recognition clue: a task-focused interface hides multi-step subsystem orchestration.

## Facade Pattern Card

A checklist for simplifying a complex subsystem.

## Problem

Clients must know too many subsystem objects and steps.

## Participants

Client Facade Subsystem classes Existing interfaces

## Core Idea

Offer high-level operations that delegate to subsystem components.

In This Lecture HomeTheaterFacade watchMovie() endMovie() Amplifier / Player / Lights Key Principles Reduce client coupling Keep advanced access

Facade presents a unified, simplified interface to a subsystem.

A Facade simplifies access; it does not prohibit subsystem use.