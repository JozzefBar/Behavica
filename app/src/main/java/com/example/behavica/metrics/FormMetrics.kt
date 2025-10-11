package com.example.behavica.metrics

import com.example.behavica.model.TouchPoint

class FormMetrics {
    // Behavioral data
    var userAgeStartTime: Long = 0
    var userAgeEndTime: Long = 0
    var userAgeEditCount: Int = 0

    var genderSelectTime: Long = 0
    var checkboxClickTime: Long = 0
    var submitClickTime: Long = 0
    var formStartTime: Long = 0

    //var userIdTypingTime: Long = 0     //for now without use

    val keystrokes: MutableList<Map<String, Any>> = mutableListOf()

    fun markFormStart() {
        formStartTime = System.currentTimeMillis()
    }

    fun markSubmitClick() {
        submitClickTime = System.currentTimeMillis()
    }

    // Improved behavioral data
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

        val timeToSubmitSec = if (submitClickTime > formStartTime && formStartTime > 0)
            (submitClickTime - formStartTime) / 1000.0
        else -1.0

        return hashMapOf(
            "userAgeTypingTime" to userAgeTypingSec,
            "userAgeEditCount" to userAgeEditCount,
            "timeToSelectGender" to timeToSelectGenderSec,
            "timeToClickCheckbox" to timeToClickCheckbox,
            "timeToSubmit" to timeToSubmitSec,
            "totalFormTime" to totalFormTimeSec,
            "touchPointsCount" to touchPoints.size,
            "touchPoints" to touchPoints.map { tp ->
                mapOf(
                    "pressure" to tp.pressure,
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