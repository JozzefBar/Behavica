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
import android.widget.FrameLayout
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

    private var startCircle: View? = null
    private var endCircle: View? = null
    private var draggableCircle: View? = null

    private var initialX = 0f
    private var initialY = 0f
    private var dX = 0f
    private var dY = 0f

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

        // Watchers and Listeners
        attachUserAgeWatcher()
        attachSpinnerListener()
        attachCheckboxListener()
        attachTouchListeners()
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

    private fun attachSpinnerListener() {
        genderSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) {
                if (pos > 0 && formMetrics.genderSelectTime == 0L)
                    formMetrics.genderSelectTime = System.currentTimeMillis()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    fun attachDragTracking(
        draggable: View,
        start: View,
        end: View,
        container: FrameLayout
    ) {
        draggableCircle = draggable
        startCircle = start
        endCircle = end

        // Reset position to start
        draggable.post {
            val startLoc = IntArray(2)
            start.getLocationInWindow(startLoc)

            val containerLoc = IntArray(2)
            container.getLocationInWindow(containerLoc)

            draggable.x = (startLoc[0] - containerLoc[0]).toFloat()
            draggable.y = (startLoc[1] - containerLoc[1]).toFloat()
        }

        draggable.setOnTouchListener { v, event ->
            recordTouchPoint(event, "dragTest")

            // If drag is already completed, ignore further touches
            if (formMetrics.dragCompleted) {
                return@setOnTouchListener true
            }

            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    formMetrics.handleDragEvent(MotionEvent.ACTION_DOWN, draggable, end)

                    // Store initial position
                    initialX = v.x
                    initialY = v.y
                    dX = v.x - event.rawX
                    dY = v.y - event.rawY

                    v.alpha = 0.8f
                }

                MotionEvent.ACTION_MOVE -> {
                    formMetrics.handleDragEvent(MotionEvent.ACTION_MOVE, draggable, end)

                    // Calculate new position
                    val newX = event.rawX + dX
                    val newY = event.rawY + dY

                    // Constrain to parent bounds
                    val containerWidth = container.width
                    val containerHeight = container.height
                    val viewWidth = v.width
                    val viewHeight = v.height

                    v.x = newX.coerceIn(0f, (containerWidth - viewWidth).toFloat())
                    v.y = newY.coerceIn(0f, (containerHeight - viewHeight).toFloat())
                }

                MotionEvent.ACTION_UP -> {
                    formMetrics.handleDragEvent(MotionEvent.ACTION_UP, draggable, end)

                    v.alpha = 1f

                    // Check if completed successfully, if not reset to start position
                    if (formMetrics.dragCompleted) {
                        v.isEnabled = false
                    } else {
                        v.animate()
                            .x(initialX)
                            .y(initialY)
                            .setDuration(300)
                            .start()
                    }
                }
            }
            true
        }
    }

    private fun attachCheckboxListener() {
        checkBox.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && formMetrics.checkboxClickTime == 0L)
                formMetrics.checkboxClickTime = System.currentTimeMillis()
        }
    }

    private fun attachTouchListeners() {
        addTouchListener(userAgeInput, "userAgeInput")
        addTouchListener(genderSpinner, "genderSpinner")
        addTouchListener(checkBox, "checkBox")
        addTouchListener(submitButton, "submitButton")
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun addTouchListener(view: View, targetName: String){
        view.setOnTouchListener { _, e ->
            recordTouchPoint(e, targetName)
            false
        }
    }

    private fun recordTouchPoint(e: MotionEvent, targetName: String) {
        val tsString = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault()).format(Date())

        val epochMs = System.currentTimeMillis()
        val actionStr = TouchPoint.actionToString(e.actionMasked)

        val idx = when (e.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN,
            MotionEvent.ACTION_POINTER_UP -> e.actionIndex
            else -> 0
        }.coerceIn(0, e.pointerCount - 1)

        val pressure = safe { e.getPressure(idx) } ?: e.pressure
        val size = safe { e.getSize(idx) } ?: e.size
        val xLocal = safe { e.getX(idx) } ?: e.x
        val yLocal = safe { e.getY(idx) } ?: e.y

        val rawX: Float
        val rawY: Float
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            rawX = safe { e.getRawX(idx) } ?: e.rawX
            rawY = safe { e.getRawY(idx) } ?: e.rawY
        }
        else {
            rawX = -1f
            rawY = -1f
        }

        val touchMajor = safe { e.getTouchMajor(idx) } ?: e.touchMajor
        val touchMinor = safe { e.getTouchMinor(idx) } ?: e.touchMinor
        val pointerId = (safe { e.getPointerId(idx) } ?: -1).toString()

        touchPoints.add(
            TouchPoint(
                pressure = pressure,
                size = size,
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
    }

    private inline fun <T> safe(block: () -> T): T? =
        try {
            block()
        } catch (_: Throwable) {
            null
        }

    fun getTouchPoints(): List<TouchPoint> = touchPoints
}