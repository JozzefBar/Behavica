package com.example.behavica.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.widget.Toast
import kotlin.math.*

class HandDetector(private val context: Context) : SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var gravitySensor: Sensor? = null
    private var linearAccSensor: Sensor? = null
    private var gyroscope: Sensor? = null

    private var gravity = FloatArray(3)
    private var linearAcc = FloatArray(3)
    private var handState = "unknown"
    private var confidence = 0f
    private var debounceCounter = 0

    companion object {
        private const val ALPHA = 0.9f
        private const val WINDOW_SIZE = 20
        private const val MIN_CONF = 0.6f
        private const val DEBOUNCE_LIMIT = 3
    }

    private val gyroBuffer = mutableListOf<Float>()

    fun start() {
        sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        gravitySensor = sensorManager.getDefaultSensor(Sensor.TYPE_GRAVITY)
        linearAccSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)
        gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        gravitySensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }
        linearAccSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }
        gyroscope?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }

        handState = "unknown"
        confidence = 0f
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    fun currentHand(): String = handState

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return

        when (event.sensor.type) {
            Sensor.TYPE_GRAVITY -> {
                for (i in 0..2)
                    gravity[i] = ALPHA * gravity[i] + (1 - ALPHA) * event.values[i]
            }

            Sensor.TYPE_LINEAR_ACCELERATION -> {
                for (i in 0..2)
                    linearAcc[i] = ALPHA * linearAcc[i] + (1 - ALPHA) * event.values[i]
            }

            Sensor.TYPE_GYROSCOPE -> {
                val norm = sqrt(
                    event.values[0].pow(2) +
                            event.values[1].pow(2) +
                            event.values[2].pow(2)
                )
                gyroBuffer.add(norm)
                if (gyroBuffer.size > WINDOW_SIZE) gyroBuffer.removeAt(0)
            }
        }

        if (gyroBuffer.size == WINDOW_SIZE) detectHand()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun detectHand() {
        val avgGyro = gyroBuffer.average().toFloat()
        val linearNorm = sqrt(linearAcc.map { it * it }.sum())
        val gx = gravity[0]
        val gy = gravity[1]
        val gz = gravity[2]

        // Telefón úplne položený alebo extrémne stabilný → UNKNOWN
        if ((avgGyro < 0.03f && linearNorm < 0.05f) || abs(gz) > 9.5f) {
            updateHand("unknown", 1f)
            return
        }

        // Both hands – mierne naklonenie, stabilnejšie
        if (avgGyro < 0.25f && abs(gx) < 2.0f && abs(gy) in 0.4f..5f) {
            val conf = calculateConfidence(avgGyro, linearNorm, abs(gy))
            updateHand("both_hands", conf)
            return
        }

        // Left hand – naklonenie doľava
        if (gx > 0.8f) {
            val conf = calculateConfidence(avgGyro, linearNorm, gx)
            updateHand("left", conf)
            return
        }

        // Right hand – naklonenie doprava
        if (gx < -0.8f) {
            val conf = calculateConfidence(avgGyro, linearNorm, abs(gx))
            updateHand("right", conf)
            return
        }

        // Default fallback – nejasný stav
        updateHand("unknown", 0.4f)
    }

    private fun calculateConfidence(gyro: Float, linAcc: Float, tilt: Float): Float {
        val stability = (1f - gyro.coerceIn(0f, 1f)) // čím menší pohyb, tým väčšia stabilita
        val motionFactor = (linAcc / 2.5f).coerceIn(0f, 1f)
        val tiltFactor = (tilt / 5f).coerceIn(0f, 1f)
        // vyvážený mix faktorov
        return (stability * 0.4f + (1 - motionFactor) * 0.3f + tiltFactor * 0.3f).coerceIn(0f, 1f)
    }

    private fun updateHand(newHand: String, conf: Float) {
        if (newHand == handState) {
            // Ak rovnaký stav, vyhladzujeme confidence
            confidence = confidence * 0.7f + conf * 0.3f
            debounceCounter = 0
        } else {
            debounceCounter++
            if (debounceCounter >= DEBOUNCE_LIMIT && conf > MIN_CONF) {
                handState = newHand
                confidence = conf
                debounceCounter = 0
                Toast.makeText(
                    context,
                    "Hand: $handState (${(confidence * 100).toInt()}%)",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }
}
