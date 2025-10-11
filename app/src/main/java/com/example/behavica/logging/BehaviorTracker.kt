package com.example.behavica.logging

import android.annotation.SuppressLint
import android.os.Build
import android.text.Editable
import android.text.TextWatcher
import android.view.MotionEvent
import android.view.View
import android.widget.AdapterView
import android.widget.Button
import android.widget.CheckBox
import android.widget.Spinner
import com.example.behavica.metrics.FormMetrics
import com.example.behavica.model.TouchPoint
import com.google.android.material.textfield.TextInputEditText
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class BehaviorTracker(private val formMetrics: FormMetrics) {

    private val touchPoints: MutableList<TouchPoint> = mutableListOf()

    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkBox: CheckBox
    private lateinit var submitButton: Button

    fun attach(
        inputAge: TextInputEditText,
        spinner: Spinner,
        checkbox: CheckBox,
        submit: Button,
    ) {
        userAgeInput = inputAge
        genderSpinner = spinner
        checkBox = checkbox
        submitButton = submit

        //TEXT WATCHERS
        attachUserAgeWatcher()

        // Gender
        genderSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) {
                if (pos > 0 && formMetrics.genderSelectTime == 0L) {
                    formMetrics.genderSelectTime = System.currentTimeMillis()
                }
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        //Checkbox
        checkBox.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && formMetrics.checkboxClickTime == 0L) {
                formMetrics.checkboxClickTime = System.currentTimeMillis()
            }
        }

        //Touch listeners
        addTouchListener(userAgeInput, "userAgeInput")
        addTouchListener(genderSpinner, "genderSpinner")
        addTouchListener(checkBox, "checkBox")
        addTouchListener(submitButton, "submitButton")
    }

    private fun attachUserAgeWatcher() {
        var lastLen = userAgeInput.text?.length ?: 0
        var startTypingAt = 0L
        userAgeInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val now = System.currentTimeMillis()
                val curLen = s?.length ?: 0

                if (startTypingAt == 0L) startTypingAt = now
                if (formMetrics.userAgeStartTime == 0L) formMetrics.userAgeStartTime = now
                formMetrics.userAgeEndTime = now

                if (curLen != lastLen) formMetrics.userAgeEditCount += 1

                val delta = curLen - lastLen
                if (delta != 0) {
                    formMetrics.keystrokes.add(
                        mapOf(
                            "field" to "userAge",
                            "type" to if (delta > 0) "insert" else "delete",
                            "count" to kotlin.math.abs(delta),
                            "t" to now
                        )
                    )
                }
                lastLen = curLen
            }
        })
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun addTouchListener(view: View, targetName: String){
        view.setOnTouchListener { _, e ->
            val tsString = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault())
                .format(Date())

            val epochMs = System.currentTimeMillis()

            val actionStr = TouchPoint.actionToString(e.actionMasked)

            val idx = when (e.actionMasked) {
                MotionEvent.ACTION_POINTER_DOWN,
                MotionEvent.ACTION_POINTER_UP -> e.actionIndex

                else -> 0
            }.coerceIn(0, e.pointerCount - 1)

            val pressure = safe { e.getPressure(idx) } ?: e.pressure
            val xLocal = safe { e.getX(idx) } ?: e.x
            val yLocal = safe { e.getY(idx) } ?: e.y

            val rawX: Float
            val rawY: Float
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                rawX = safe { e.getRawX(idx) } ?: -1f
                rawY = safe { e.getRawY(idx) } ?: -1f
            } else {
                rawX = -1f
                rawY = -1f
            }

            val touchMajor = safe { e.getTouchMajor(idx) } ?: -1f
            val touchMinor = safe { e.getTouchMinor(idx) } ?: -1f
            val pointerId = (safe { e.getPointerId(idx) } ?: -1).toString()

            touchPoints.add(
                TouchPoint(
                    pressure = pressure,
                    x = xLocal,
                    y = yLocal,
                    timestampTime = tsString,
                    target = targetName,
                    timestampEpochMs = epochMs,
                    action = actionStr,
                    pointerId = pointerId,
                    rawX = rawX,
                    rawY = rawY,
                    touchMajor = touchMajor,
                    touchMinor = touchMinor
                )
            )
            false
        }
    }

    private inline fun <T> safe(block: () -> T): T? =
        try {
            block()
        } catch (_: Throwable) {
            null
        }

    fun getTouchPoints(): List<TouchPoint> = touchPoints
}