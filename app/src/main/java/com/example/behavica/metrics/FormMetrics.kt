package com.example.behavica.metrics

import android.view.MotionEvent
import android.view.View
import com.example.behavica.model.TouchPoint
import kotlin.math.pow
import kotlin.math.sqrt

class FormMetrics {
    // Behavioral data
    var userAgeStartTime: Long = 0
    var userAgeEndTime: Long = 0
    var userAgeEditCount: Int = 0

    var genderSelectTime: Long = 0
    var checkboxClickTime: Long = 0
    var submitClickTime: Long = 0
    var formStartTime: Long = 0

    val keystrokes: MutableList<Map<String, Any>> = mutableListOf()

    fun markFormStart() {
        formStartTime = System.currentTimeMillis()
    }

    fun markSubmitClick() {
        submitClickTime = System.currentTimeMillis()
    }

    // Internal for drag test
    var dragStartTime: Long = 0
    var dragEndTime: Long = 0
    var dragCompleted: Boolean = false
    var dragAttempts: Int = 0
    var dragDistance: Float = 0f
    var dragPathLength: Float = 0f
    private var lastMoveX: Float = 0f
    private var lastMoveY: Float = 0f

    // Callback for drag status changes
    var onDragStatusChanged: ((completed: Boolean) -> Unit)? = null

    // Unified handling of the drag-circle motion
    fun handleDragEvent(
        action: Int,
        draggableCircle: View,
        endCircle: View
    ) {
        when (action) {
            MotionEvent.ACTION_DOWN -> {
                dragStartTime = System.currentTimeMillis()
                dragAttempts++
                dragCompleted = false
                dragDistance = 0f
                dragPathLength = 0f

                // Initialize last position for path tracking
                val draggableLoc = IntArray(2)
                draggableCircle.getLocationInWindow(draggableLoc)
                lastMoveX = draggableLoc[0] + draggableCircle.width / 2f
                lastMoveY = draggableLoc[1] + draggableCircle.height / 2f
            }

            MotionEvent.ACTION_MOVE -> {
                // Calculate incremental distance traveled for path length analytics
                val draggableLoc = IntArray(2)
                draggableCircle.getLocationInWindow(draggableLoc)

                val currentX = draggableLoc[0] + draggableCircle.width / 2f
                val currentY = draggableLoc[1] + draggableCircle.height / 2f

                // Calculate distance from last position
                val incrementalDistance = sqrt(
                    (currentX - lastMoveX).pow(2) + (currentY - lastMoveY).pow(2)
                )

                // Add to total path length
                dragPathLength += incrementalDistance

                // Update last position for next calculation
                lastMoveX = currentX
                lastMoveY = currentY
            }

            MotionEvent.ACTION_UP -> {
                dragEndTime = System.currentTimeMillis()

                // Get positions in window coordinates
                val draggableLoc = IntArray(2)
                draggableCircle.getLocationInWindow(draggableLoc)

                val endLoc = IntArray(2)
                endCircle.getLocationInWindow(endLoc)

                // Calculate center points
                val draggableCenterX = draggableLoc[0] + draggableCircle.width / 2f
                val draggableCenterY = draggableLoc[1] + draggableCircle.height / 2f

                val endCenterX = endLoc[0] + endCircle.width / 2f
                val endCenterY = endLoc[1] + endCircle.height / 2f

                // Calculate distance between centers
                val distance = sqrt(
                    (draggableCenterX - endCenterX).pow(2) + (draggableCenterY - endCenterY).pow(2)
                )

                dragDistance = distance

                // Consider completed if within a reasonable threshold - 70% of the circle's width
                val threshold = endCircle.width * 0.7f
                dragCompleted = distance < threshold

                onDragStatusChanged?.invoke(dragCompleted)
            }
        }
    }

    // Building behavioral data
    fun buildBehaviorData(touchPoints: List<TouchPoint>): Map<String, Any> {
        val totalFormTimeSec = if (formStartTime > 0)
            (System.currentTimeMillis() - formStartTime) / 1000.0
        else -1.0

        val userAgeTypingSec = if (userAgeEndTime > userAgeStartTime && userAgeStartTime > 0)
            (userAgeEndTime - userAgeStartTime) / 1000.0
        else -1.0

        val timeToSelectGenderSec = if (genderSelectTime > formStartTime && formStartTime > 0)
            (genderSelectTime - formStartTime) / 1000.0
        else -1.0

        val timeToClickCheckbox = if (checkboxClickTime > formStartTime && formStartTime > 0)
            (checkboxClickTime - formStartTime) / 1000.0
        else -1.0

        val timeToFinishDragTest = if (dragStartTime > 0 && dragEndTime > dragStartTime)
            (dragEndTime - dragStartTime) / 1000.0
        else -1.0

        val timeToSubmitSec = if (submitClickTime > formStartTime && formStartTime > 0)
            (submitClickTime - formStartTime) / 1000.0
        else -1.0

        return hashMapOf(
            "userAgeTypingTime" to userAgeTypingSec,
            "userAgeEditCount" to userAgeEditCount,
            "timeToSelectGender" to timeToSelectGenderSec,
            "timeToClickCheckbox" to timeToClickCheckbox,
            "timeToSubmit" to timeToSubmitSec,
            "dragDurationSec" to timeToFinishDragTest,
            "dragAttempts" to dragAttempts,
            "dragDistance" to dragDistance,
            "dragPathLength" to dragPathLength,
            "totalFormTime" to totalFormTimeSec,
            "touchPointsCount" to touchPoints.size,
            "touchPoints" to touchPoints.map { tp ->
                mapOf(
                    "pressure" to tp.pressure,
                    "size" to tp.size,
                    "x" to tp.x,
                    "y" to tp.y,
                    "rawX" to tp.rawX,
                    "rawY" to tp.rawY,
                    "touchMajor" to tp.touchMajor,
                    "touchMinor" to tp.touchMinor,
                    "timestampTime" to tp.timestampTime,
                    "timestampEpochMs" to tp.timestampEpochMs,
                    "action" to tp.action,
                    "pointerId" to tp.pointerId,
                    "target" to tp.target
                )
            },
            "keystrokes" to keystrokes
        )
    }
}