package com.example.behavica.model

import android.view.MotionEvent

data class TouchPoint(
    val pressure: Float,
    val x: Float,
    val y: Float,
    val timestampTime: String,
    val target: String,
    val timestampEpochMs: Long,
    val action: String,
    val pointerId: String,
    val rawX: Float,
    val rawY: Float,
    val touchMajor: Float,
    val touchMinor: Float
){
    companion object{
        fun actionToString(actionMasked: Int): String = when (actionMasked) {
            MotionEvent.ACTION_DOWN -> "ACTION_DOWN"
            MotionEvent.ACTION_UP -> "ACTION_UP"
            MotionEvent.ACTION_CANCEL -> "ACTION_CANCEL"
            MotionEvent.ACTION_MOVE -> "ACTION_MOVE"
            MotionEvent.ACTION_POINTER_DOWN -> "ACTION_POINTER_DOWN"
            MotionEvent.ACTION_POINTER_UP -> "ACTION_POINTER_UP"
            else -> "ACTION_OTHER"
        }
    }
}