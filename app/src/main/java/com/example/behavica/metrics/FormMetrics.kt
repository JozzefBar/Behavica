package com.example.behavica.metrics

import com.example.behavica.model.TouchPoint

class FormMetrics {
    // Behavioral data
    var userIdStartTime: Long = 0
    var userIdEndTime: Long = 0
    var userIdEditCount = 0
    var userIdMaxLength = 0

    var userAgeStartTime: Long = 0
    var userAgeEndTime: Long = 0
    var userAgeEditCount = 0

    var genderSelectTime: Long = 0
    var checkboxClickTime: Long = 0
    var submitClickTime: Long = 0
    var formStartTime: Long = 0

    fun markFormStart() { formStartTime = System.currentTimeMillis() }
    fun markSubmitClick() { submitClickTime = System.currentTimeMillis() }

    // Improved behavioral data
    fun buildBehaviorData(userId: String, touchPoints: List<TouchPoint>): Map<String, Any?> {
        val userIdTypingTime = if (userIdEndTime > userIdStartTime) userIdEndTime - userIdStartTime else -1
        val userAgeTypingTime = if (userAgeEndTime > userAgeStartTime) userAgeEndTime - userAgeStartTime else -1

        return hashMapOf(
            "totalFormTime" to ((System.currentTimeMillis() - formStartTime) / 1000.0),
            "userIdTypingTime" to (if (userIdTypingTime > 0) userIdTypingTime / 1000.0 else -1.0),
            "userIdEditCount" to userIdEditCount,
            "userIdMaxLength" to userIdMaxLength,
            "userAgeTypingTime" to (if (userAgeTypingTime > 0) userAgeTypingTime / 1000.0 else -1.0),
            "userAgeEditCount" to userAgeEditCount,
            "timeToSelectGender" to (if (genderSelectTime > 0) (genderSelectTime - formStartTime) / 1000.0 else -1.0),
            "timeToCheckbox" to (if (checkboxClickTime > 0) (checkboxClickTime - formStartTime) / 1000.0 else -1.0),
            "timeToSubmit" to (if (submitClickTime > 0) (submitClickTime - formStartTime) / 1000.0 else -1.0),
            "averageTypingSpeed" to (if (userIdTypingTime > 0) (userId.length.toDouble() / (userIdTypingTime / 1000.0)) else -1.0),
            "touchPointsCount" to touchPoints.size,
            "touchPoints" to touchPoints.map {
                mapOf(
                    "pressure" to it.pressure,
                    "x" to it.x,
                    "y" to it.y,
                    "timestamp" to it.timestampTime,
                    "target" to it.target
                )
            }
        )
    }
}