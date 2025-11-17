package com.example.behavica.sensors

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import com.example.behavica.model.SensorReading

class SensorDataCollector(private val context: Context) : SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var gyroscope: Sensor? = null

    private val sensorReadings = mutableListOf<SensorReading>()

    private var lastSampleTime = 0L
    private val sampleIntervalMs = 100L

    companion object {
        private const val ALPHA = 0.8f
    }

    private var smoothedAccel = FloatArray(3) { 0f }
    private var smoothedGyro = FloatArray(3) { 0f }

    private var hasNewAccelData = false
    private var hasNewGyroData = false

    fun start() {
        sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }
        gyroscope?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }

        sensorReadings.clear()
        lastSampleTime = System.currentTimeMillis()
        smoothedAccel = FloatArray(3) { 0f }
        smoothedGyro = FloatArray(3) { 0f }
        hasNewAccelData = false
        hasNewGyroData = false
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return

        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                for (i in 0..2) {
                    smoothedAccel[i] = ALPHA * smoothedAccel[i] + (1 - ALPHA) * event.values[i]
                }
                hasNewAccelData = true
            }

            Sensor.TYPE_GYROSCOPE -> {
                for (i in 0..2) {
                    smoothedGyro[i] = ALPHA * smoothedGyro[i] + (1 - ALPHA) * event.values[i]
                }
                hasNewGyroData = true
            }
        }

        val currentTime = System.currentTimeMillis()
        if (currentTime - lastSampleTime >= sampleIntervalMs && hasNewAccelData && hasNewGyroData) {
            sensorReadings.add(
                SensorReading(
                    timestamp = currentTime,
                    accelX = smoothedAccel[0],
                    accelY = smoothedAccel[1],
                    accelZ = smoothedAccel[2],
                    gyroX = smoothedGyro[0],
                    gyroY = smoothedGyro[1],
                    gyroZ = smoothedGyro[2]
                )
            )
            lastSampleTime = currentTime
            hasNewAccelData = false
            hasNewGyroData = false
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    fun getSensorData(): List<SensorReading> = sensorReadings.toList()
}