package com.example.behavica.data

import com.example.behavica.model.SensorReading
import com.example.behavica.model.TouchPoint
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException

//Sends behavioral data to the Firebase Cloud Function and returns an authentication result.
//Flow: Android collects raw data → sends JSON POST → Cloud Function extracts features
//       → runs distance-based model → returns accepted/rejected with score
class AuthApiClient {

    data class AuthResult(
        val accepted: Boolean,
        val score: Double,
        val email: String,
        val allScores: Map<String, Double>,
        val error: String?
    )

    private val client = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val functionUrl = Config.AUTH_FUNCTION_URL

    //Asynchronously sends behavioral data to the Cloud Function.
    fun authenticate(
        userId: String,
        submissionDurationSec: Double,
        dragAttempts: Int,
        dragDistance: Float,
        dragPathLength: Float,
        dragDurationSec: Double,
        textRewriteTime: Double,
        averageWordTime: Double,
        textEditCount: Int,
        touchPoints: List<TouchPoint>,
        keystrokes: List<Map<String, Any>>,
        sensorData: List<SensorReading>,
        onResult: (AuthResult) -> Unit,
        onError: (String) -> Unit
    ) {
        val json = buildRequestJson(
            userId, submissionDurationSec, dragAttempts, dragDistance, dragPathLength,
            dragDurationSec, textRewriteTime, averageWordTime, textEditCount,
            touchPoints, keystrokes, sensorData
        )
        val body = json.toString().toRequestBody(jsonMediaType)
        val request = Request.Builder().url(functionUrl).post(body).build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                onError("Network error: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                val bodyStr = response.body?.string()
                if (!response.isSuccessful || bodyStr == null) {
                    onError("Server error: ${response.code}")
                    return
                }
                try {
                    val obj      = JSONObject(bodyStr)
                    val accepted = obj.getBoolean("accepted")
                    val score    = obj.getDouble("score")
                    val email    = obj.getString("email")

                    val allScoresJson = obj.getJSONObject("allScores")
                    val allScores = allScoresJson.keys().asSequence().associate { key ->
                        key to allScoresJson.getDouble(key)
                    }

                    val error = if (obj.has("error")) obj.getString("error") else null
                    onResult(AuthResult(accepted, score, email, allScores, error))
                } catch (e: Exception) {
                    onError("Response parsing error: ${e.message}")
                }
            }
        })
    }

    // JSON request body builders

    private fun buildRequestJson(
        userId: String,
        submissionDurationSec: Double,
        dragAttempts: Int,
        dragDistance: Float,
        dragPathLength: Float,
        dragDurationSec: Double,
        textRewriteTime: Double,
        averageWordTime: Double,
        textEditCount: Int,
        touchPoints: List<TouchPoint>,
        keystrokes: List<Map<String, Any>>,
        sensorData: List<SensorReading>
    ): JSONObject {
        return JSONObject().apply {
            put("userId",      userId)
            put("basic",       buildBasicJson(
                submissionDurationSec, dragAttempts, dragDistance, dragPathLength,
                dragDurationSec, textRewriteTime, averageWordTime, textEditCount,
                touchPoints.size, sensorData.size
            ))
            put("touchPoints", buildTouchPointsJson(touchPoints))
            put("keystrokes",  buildKeystrokesJson(keystrokes))
            put("sensorData",  buildSensorDataJson(sensorData))
        }
    }

    private fun buildBasicJson(
        submissionDurationSec: Double,
        dragAttempts: Int,
        dragDistance: Float,
        dragPathLength: Float,
        dragDurationSec: Double,
        textRewriteTime: Double,
        averageWordTime: Double,
        textEditCount: Int,
        touchPointsCount: Int,
        sensorDataCount: Int
    ): JSONObject {
        return JSONObject().apply {
            put("submissionDurationSec", submissionDurationSec)
            put("dragAttempts",          dragAttempts)
            put("dragDistance",          dragDistance)
            put("dragPathLength",        dragPathLength)
            put("dragDurationSec",       dragDurationSec)
            put("textRewriteTime",       textRewriteTime)
            put("averageWordTime",       averageWordTime)
            put("textEditCount",         textEditCount)
            put("touchPointsCount",      touchPointsCount)
            put("sensorDataCount",       sensorDataCount)
        }
    }

    private fun buildTouchPointsJson(touchPoints: List<TouchPoint>): JSONArray {
        return JSONArray().apply {
            touchPoints.forEach { tp ->
                put(JSONObject().apply {
                    put("timestamp",  tp.timestamp)
                    put("pressure",   tp.pressure)
                    put("size",       tp.size)
                    put("touchMajor", tp.touchMajor)
                    put("touchMinor", tp.touchMinor)
                    put("x",          tp.x)
                    put("y",          tp.y)
                    put("action",     tp.action)
                    put("target",     tp.target)
                })
            }
        }
    }

    private fun buildKeystrokesJson(keystrokes: List<Map<String, Any>>): JSONArray {
        return JSONArray().apply {
            keystrokes.forEach { ks ->
                put(JSONObject().apply {
                    put("timestamp", ks["timestamp"])
                    put("type",      ks["type"])
                    put("word",      ks["word"])
                    put("count",     ks["count"])
                })
            }
        }
    }

    private fun buildSensorDataJson(sensorData: List<SensorReading>): JSONArray {
        return JSONArray().apply {
            sensorData.forEach { sd ->
                put(JSONObject().apply {
                    put("accelX", sd.accelX)
                    put("accelY", sd.accelY)
                    put("accelZ", sd.accelZ)
                    put("gyroX",  sd.gyroX)
                    put("gyroY",  sd.gyroY)
                    put("gyroZ",  sd.gyroZ)
                })
            }
        }
    }
}
