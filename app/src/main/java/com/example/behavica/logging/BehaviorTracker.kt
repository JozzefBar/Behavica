package com.example.behavica.logging

import android.annotation.SuppressLint
import android.os.Build
import android.text.Editable
import android.text.TextWatcher
import android.view.MotionEvent
import android.view.View
import android.widget.CheckBox
import android.widget.FrameLayout
import com.example.behavica.model.TouchPoint
import com.google.android.material.textfield.TextInputEditText
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.pow
import kotlin.math.sqrt

class BehaviorTracker() {

    private val touchPoints: MutableList<TouchPoint> = mutableListOf()
    private val keystrokes: MutableList<Map<String, Any>> = mutableListOf()

    //Drag test metrics
    var dragStartTime: Long = 0
    var dragEndTime: Long = 0
    var dragCompleted: Boolean = false
    var dragAttempts: Int = 0
    var dragDistance: Float = 0f
    var dragPathLength: Float = 0f
    private var lastMoveX: Float = 0f
    private var lastMoveY: Float = 0f

    // Text copy metrics
    var textStartTime: Long = 0
    var textEditCount = 0

    // checkbox metrics
    var checkboxChecked = false

    // callbacks
    var onDragStatusChanged: ((completed: Boolean) -> Unit)? = null

    @SuppressLint("ClickableViewAccessibility")
    fun attachTouchListener(view : View, targetName: String){
        view.setOnTouchListener { _, e ->
            recordTouchPoint(e, targetName)
            false
        }
    }

    fun attachTextWatcher(editText: TextInputEditText) {
        var lastLen = editText.text?.length ?: 0

        editText.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val now = System.currentTimeMillis()
                val curLen = s?.length ?: 0

                if (textStartTime == 0L && curLen > 0)
                    textStartTime = now

                if (curLen != lastLen)
                    textEditCount++

                val delta = curLen - lastLen
                if (delta != 0) {
                    keystrokes.add(
                        mapOf(
                            "field" to "rewriteTextInput",
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

    fun attachCheckboxListener(checkBox: CheckBox) {
        checkBox.setOnCheckedChangeListener { _, isChecked ->
            checkboxChecked = isChecked
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    fun attachDragTracking(
        draggable: View,
        start: View,
        end: View,
        container: FrameLayout,
    ) {
        var initialX = 0f
        var initialY = 0f
        var dX = 0f
        var dY = 0f

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
            if (dragCompleted) {
                return@setOnTouchListener true
            }

            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    handleDragEvent(MotionEvent.ACTION_DOWN, draggable, end)

                    // Store initial position
                    initialX = v.x
                    initialY = v.y
                    dX = v.x - event.rawX
                    dY = v.y - event.rawY

                    v.alpha = 0.8f
                }

                MotionEvent.ACTION_MOVE -> {
                    handleDragEvent(MotionEvent.ACTION_MOVE, draggable, end)

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
                    handleDragEvent(MotionEvent.ACTION_UP, draggable, end)

                    v.alpha = 1f

                    // Check if completed successfully, if not reset to start position
                    if (dragCompleted) {
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

    private fun recordTouchPoint(e: MotionEvent, targetName: String) {
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault())
        dateFormat.timeZone = TimeZone.getTimeZone("Europe/Bratislava")
        val tsString = dateFormat.format(Date())

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

    fun getDragDurationSec(): Double {
        return if (dragStartTime > 0 && dragEndTime > dragStartTime)
            (dragEndTime - dragStartTime) / 1000.0
        else -1.0
    }

    fun getTextRewriteTime(): Double {
        return if (textStartTime > 0)
            (System.currentTimeMillis() - textStartTime) / 1000.0
        else -1.0
    }

    fun getTouchPoints(): List<TouchPoint> = touchPoints

    fun getKeystrokes(): List<Map<String, Any>> = keystrokes
}