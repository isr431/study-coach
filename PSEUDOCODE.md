## Level 1 — Course Setup and Study Plan Generation

```text
MODULE CourseSetupAndStudyPlanGeneration(courseName, syllabusFile)
    IF ValidateCourseInput(courseName, syllabusFile) IS false THEN
        DISPLAY "Enter a course name and select a .txt file"
        STOP
    END IF

    syllabusText <- ReadSyllabusFile(syllabusFile)
    IF syllabusText IS EMPTY THEN
        DISPLAY "The syllabus could not be read or is empty"
        STOP
    END IF

    topicPlan <- RequestTopicPlan(courseName, syllabusText)
    IF ValidateTopicPlan(topicPlan) IS false THEN
        DISPLAY "A valid topic plan could not be generated"
        STOP
    END IF

    SaveCourseAndTopics(courseName, syllabusText, topicPlan)
    DISPLAY topicPlan
END MODULE
```

## Level 2 — Validate Course Input

```text
MODULE ValidateCourseInput(courseName, syllabusFile)
    IF courseName IS EMPTY THEN
        RETURN false
    END IF

    IF syllabusFile DOES NOT EXIST OR is not a .txt file THEN
        RETURN false
    END IF

    RETURN true
END MODULE
```

## Level 2 — Read Syllabus File

```text
MODULE ReadSyllabusFile(syllabusFile)
    TRY
        syllabusText <- READ syllabusFile
        RETURN TRIM(syllabusText)
    CATCH fileError
        RETURN EMPTY
    END TRY
END MODULE
```

## Level 2 — Request Topic Plan

```text
MODULE RequestTopicPlan(courseName, syllabusText)
    CREATE prompt using courseName and syllabusText
    ASK OpenRouter for an ordered JSON list of topic titles and summaries

    IF the request fails THEN
        RETURN EMPTY
    END IF

    RETURN the AI response
END MODULE
```

## Level 2 — Validate Topic Plan

```text
MODULE ValidateTopicPlan(topicPlan)
    IF topicPlan is not a non-empty JSON list THEN
        RETURN false
    END IF

    FOR EACH topic IN topicPlan
        IF topic title OR summary IS EMPTY THEN
            RETURN false
        END IF
    END FOR

    RETURN true
END MODULE
```

## Level 2 — Save Course and Topics

```text
MODULE SaveCourseAndTopics(courseName, syllabusText, topicPlan)
    DELETE the existing course and topics
    SAVE courseName and syllabusText

    FOR EACH topic IN topicPlan
        SAVE its title, summary, order and incomplete status
    END FOR
END MODULE
```
