package com.example.behavica.ui

import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.behavica.R
import kotlin.math.roundToInt

/**
 * Displays the detailed result of biometric authentication.
 *
 * Receives data via Intent extras from SubmissionActivity after calling the Cloud Function:
 *   accepted         – whether the user was accepted (Boolean)
 *   score            – verification score 0..1 (Double)
 *   email            – email of the authenticated user (String)
 *   userId           – current user's ID, used to highlight their row in the table (String)
 *   allScores_keys   – IDs of all users (StringArray)
 *   allScores_values – corresponding scores (DoubleArray)
 */
class AuthResultActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_auth_result)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.auth_result_root)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        // Back button disabled – this is the final screen
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {}
        })

        // Read data from Intent extras
        val accepted      = intent.getBooleanExtra("accepted", false)
        val score         = intent.getDoubleExtra("score", 0.0)
        val email         = intent.getStringExtra("email") ?: ""
        val currentUserId = intent.getStringExtra("userId") ?: ""
        val errorMessage  = intent.getStringExtra("error")
        val keys          = intent.getStringArrayExtra("allScores_keys") ?: emptyArray()
        val values        = intent.getDoubleArrayExtra("allScores_values") ?: DoubleArray(0)

        // Reconstruct map and sort by score descending
        val allScores = keys.zip(values.toList()).sortedByDescending { it.second }

        // ── Status banner ─────────────────────────────────────────────────────
        val statusCard = findViewById<LinearLayout>(R.id.status_card)
        val statusIcon = findViewById<TextView>(R.id.status_icon)
        val statusText = findViewById<TextView>(R.id.status_text)

        if (accepted) {
            // Green = authentication accepted
            statusCard.setBackgroundColor(0xFF4CAF50.toInt())
            statusIcon.text = getString(R.string.auth_result_icon_accepted)
            statusText.text = getString(R.string.auth_result_accepted)
        } else {
            // Red = authentication rejected
            statusCard.setBackgroundColor(0xFFF44336.toInt())
            statusIcon.text = getString(R.string.auth_result_icon_rejected)
            statusText.text = if (errorMessage == "user_not_in_model") {
                getString(R.string.auth_result_user_not_in_model)
            } else {
                getString(R.string.auth_result_rejected)
            }
        }

        // ── Details ───────────────────────────────────────────────────────────
        findViewById<TextView>(R.id.email_value).text = if (email == "unknown") {
            getString(R.string.auth_result_email_unknown)
        } else {
            email
        }
        // Score as percentage using string resource (avoids setText concatenation warning)
        findViewById<TextView>(R.id.score_value).text =
            getString(R.string.auth_result_score_percent, (score * 100).roundToInt())

        // ── Scores table for all users ────────────────────────────────────────
        val colorPrimary  = ContextCompat.getColor(this, R.color.colorPrimary)
        val colorText     = ContextCompat.getColor(this, R.color.textColorPrimary)
        val colorRowAlt   = 0xFFF9F9F9.toInt()
        val colorRankText = 0xFF888888.toInt()

        val container = findViewById<LinearLayout>(R.id.scores_container)
        allScores.forEachIndexed { index, (userId, userScore) ->
            val isCurrentUser = userId == currentUserId

            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(16, 14, 16, 14)
                // Alternating row background for readability
                if (index % 2 == 0) setBackgroundColor(colorRowAlt)
            }

            // Rank column – uses string resource to avoid literal setText warning
            val rankView = TextView(this).apply {
                text = getString(R.string.auth_result_rank, index + 1)
                textSize = 13f
                setTextColor(colorRankText)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.5f)
            }

            // User ID column – current user highlighted with colorPrimary + bold
            val userView = TextView(this).apply {
                text = userId
                textSize = 14f
                setTextColor(if (isCurrentUser) colorPrimary else colorText)
                if (isCurrentUser) setTypeface(null, Typeface.BOLD)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 2f)
            }

            // Score column – percentage via string resource, highlighted for current user
            val scoreView = TextView(this).apply {
                text = getString(R.string.auth_result_score_percent, (userScore * 100).roundToInt())
                textSize = 14f
                gravity = Gravity.END
                setTextColor(if (isCurrentUser) colorPrimary else colorText)
                if (isCurrentUser) setTypeface(null, Typeface.BOLD)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }

            row.addView(rankView)
            row.addView(userView)
            row.addView(scoreView)
            container.addView(row)
        }
    }
}
