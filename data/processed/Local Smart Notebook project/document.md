## Campus Library Assistant

A Structured Test Document for Local Smart Notebook RAG

PDF edition | English | Fictional university library policy

## 1. Project Overview

Campus Library Assistant is a fictional information system designed to help university students find books, reserve study rooms, and understand library policies. This document is intentionally structured with headings, paragraphs, lists, tables, and cross-references so it can be used to test document parsing, chunking, embeddings, retrieval, reranking, and answer generation.

The system serves three campus libraries: Main Library, Engineering Library, and Medical Library. The Main Library is the only branch that operates 24 hours during examination weeks. The other branches keep their regular schedules during examination weeks.

## 2. Library Opening Hours

Regular opening hours are shown below. Times use the local campus time zone. A closing time of 20:00 means the library closes at eight o'clock in the evening.

| Branch              | Saturday-Wednesday   | Thursday    | Friday      |
|---------------------|----------------------|-------------|-------------|
| Main Library        | 08:00-22:00          | 08:00-20:00 | 10:00-18:00 |
| Engineering Library | 09:00-19:00          | 09:00-17:00 | Closed      |
| Medical Library     | 08:00-18:00          | 08:00-16:00 | 10:00-14:00 |

During the official examination period, the Main Library extends its service to 24 hours every day. This special schedule does not apply to the Engineering Library or the Medical Library. The library website displays emergency closures separately from regular opening hours.

## 3. Membership and Borrowing Rules

All currently enrolled students may borrow up to five books at a time. Faculty members may borrow up to ten books. Visiting researchers may use reading rooms but cannot borrow books unless they receive a temporary borrowing permit from the Library Director.

| Member type           |   Maximum books | Standard loan period   | Renewals       |
|-----------------------|-----------------|------------------------|----------------|
| Undergraduate student |               5 | 14 days                | 2              |
| Postgraduate student  |               5 | 21 days                | 2              |
| Faculty member        |              10 | 30 days                | 3              |
| Visiting researcher   |               0 | Reading room only      | Not applicable |

A renewal is allowed only if no other member has placed a reservation on the book. Renewals must be submitted before the current due date. A book that is overdue cannot be renewed online; the member must contact the circulation desk.

- Students must present a valid university ID when borrowing a book.
- Reference-only books cannot leave the library building.

- Course-reserve books have a maximum loan period of three hours.
- Fines are calculated per book, not per member account.

## 4. Study Room Reservations

Students can reserve group study rooms through the library portal. A reservation must be made at least 30 minutes before the requested start time and no more than seven days in advance. Each reservation lasts between 30 and 120 minutes.

A group study room requires at least two students and can hold up to six students. The person who creates the reservation is the booking owner and is responsible for checking in. Check-in opens 10 minutes before the reservation and closes 15 minutes after its start time.

If the booking owner does not check in within the allowed period, the reservation is automatically cancelled and the room becomes available to other students. A student may hold only one future group-room reservation at a time.

## 5. Late Returns and Fines

The standard overdue fine is 2 credits per book for each calendar day after the due date. The fine is capped at 40 credits per book. Friday and public holidays count as calendar days. A book returned on its due date has no overdue fine, even if it is returned after the library's normal closing time using the external return box.

Example: A student returns a book three calendar days after its due date. The fine is 6 credits. If the book is returned 30 days late, the uncapped fine would be 60 credits, but the student pays the maximum of 40 credits.

## 6. Digital Services and Support

The library portal provides catalogue search, account status, room reservations, and renewal requests. It does not support payment of fines. Fine payments must be made at the Finance Office or through the university payment gateway.

| Service           | Available online?    | Notes                                                 |
|-------------------|----------------------|-------------------------------------------------------|
| Catalogue search  | Yes                  | Search by title, author, ISBN, or subject.            |
| Room reservation  | Yes                  | Available to currently enrolled students.             |
| Book renewal      | Yes, with conditions | Unavailable for overdue or reserved books.            |
| Fine payment      | No                   | Use the Finance Office or university payment gateway. |
| Borrowing history | Yes                  | Visible only to the account owner.                    |

For account or portal problems, contact library.support@example.edu. The support team responds Sunday through Thursday, 09:00-16:00. For urgent building-safety issues, contact Campus Security rather than the library support email.

## 7. Frequently Asked Questions

- Q: Can an undergraduate student borrow seven books?

A: No. An undergraduate student may borrow a maximum of five books at a time.

- Q: Can I renew a book if another student has reserved it?

A: No. A reservation by another member prevents renewal.

- Q: Is the Engineering Library open on Friday?

A: No. The Engineering Library is closed on Friday under its regular schedule.

- Q: Can I pay a fine through the library portal?

A: No. Fine payments are handled by the Finance Office or the university payment gateway.

- Q: What happens if I miss my study-room check-in?

A: If the booking owner does not check in within 15 minutes after the reservation starts, the reservation is cancelled automatically.

## 8. Important Terms

| Term                | Definition                                                                            |
|---------------------|---------------------------------------------------------------------------------------|
| Booking owner       | The student who creates a study-room reservation and must check in.                   |
| Calendar day        | A day counted in the overdue-fine calculation, including Fridays and public holidays. |
| Course-reserve book | A book temporarily restricted for course use, with a three-hour maximum loan.         |
| Reference-only book | A book that must remain inside the library building.                                  |
| Renewal             | An extension of a book loan, subject to reservation and due-date rules.               |

Cross-reference: the room check-in cancellation rule is explained in Section 4. The fine cap and calendar-day definition are explained in Section 5. Borrowing limits and loan periods are listed in Section 3.

## 9. Test Scenarios for RAG Evaluation

Use the following scenarios to check whether a RAG system retrieves exact facts, combines information from multiple sections, respects conditions, and avoids unsupported assumptions.

- Single-fact lookup: What is the undergraduate borrowing limit?
- Multi-condition lookup: Can a postgraduate student renew an overdue book that has no reservation?
- Cross-section reasoning: During examination weeks, which library is open 24 hours, and does that schedule apply to the Engineering Library?
- Numeric reasoning: What fine is charged for a book returned 12 calendar days late?
- Table retrieval: Compare the standard loan period for undergraduate and postgraduate students.
- Negative question: Which online service is not supported by the library portal?
- Source attribution: Identify the section that defines the study-room check-in window.
- Out-of-scope question: What is the library's annual electricity consumption? The document does not provide this information.

Expected behavior: answers should be grounded in the document, preserve numerical values and conditions, cite the relevant section or page when available, and explicitly say when the requested information is not present.