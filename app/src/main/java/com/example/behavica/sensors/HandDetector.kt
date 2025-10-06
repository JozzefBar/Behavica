package com.example.behavica.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.widget.Toast
import kotlin.math.abs

class HandDetector(private val context: Context) : SensorEventListener {

    // Hand detection
    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var handHeld: String = "unknown"
    private val handBuffer = mutableListOf<Triple<Float, Float, Float>>()
    private lateinit var gravity: FloatArray

    // Sensor setup for hand detection
    fun start() {
        sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_UI)
        handHeld = "unknown" // default
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    fun currentHand(): String = handHeld

    // SensorEventListener
    override fun onSensorChanged(event: android.hardware.SensorEvent?) {
        event ?: return
        if (event.sensor.type == Sensor.TYPE_ACCELEROMETER) {
            val alpha = 0.8f
            if (!::gravity.isInitialized) gravity = FloatArray(3) { 0f }
            for (i in 0..2) gravity[i] = alpha * gravity[i] + (1 - alpha) * event.values[i]

            val x = gravity[0]; val y = gravity[1]; val z = gravity[2]

            handBuffer.add(Triple(x, y, z))
            if (handBuffer.size > 20) handBuffer.removeAt(0)

            val avgX = handBuffer.map { it.first }.average().toFloat()
            val avgY = handBuffer.map { it.second }.average().toFloat()
            val avgZ = handBuffer.map { it.third }.average().toFloat()

            val newHand = detectHand(avgX, avgY, avgZ)
            if (newHand != handHeld) {
                handHeld = newHand
                Toast.makeText(context, "Detected hand: $handHeld", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun detectHand(x: Float, y: Float, z: Float): String {
        val movementThreshold = 2.5f
        val horizontalThreshold = 1.5f

        if (abs(x) < horizontalThreshold && abs(y) < horizontalThreshold && abs(z - 9.8f) < horizontalThreshold) return "unknown"

        if (handHeld != "unknown") {
            return when {
                x > movementThreshold -> "left"
                x < -movementThreshold -> "right"
                else -> handHeld
            }
        }

        return when {
            x > movementThreshold -> "left"
            x < -movementThreshold -> "right"
            else -> handHeld
        }
    }
}
