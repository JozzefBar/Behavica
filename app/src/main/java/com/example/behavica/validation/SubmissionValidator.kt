package com.example.behavica.validation

import android.widget.CheckBox
import android.widget.Toast
import com.example.behavica.R
import com.google.android.material.textfield.TextInputEditText

class SubmissionValidator{
    fun validateSubmission(
        dragCompleted: Boolean,
        textInput: TextInputEditText,
        targetText: String,
        checkbox: CheckBox
    ):Boolean{
        val context = checkbox.context

        if(!dragCompleted) {
            Toast.makeText(context, R.string.please_complete_drag, Toast.LENGTH_LONG).show()
            return false
        }

        val enteredText = textInput.text.toString().trim()
        if(enteredText != targetText){
            Toast.makeText(context, R.string.please_rewrite_correctly, Toast.LENGTH_LONG).show()
            return false
        }

        if (!checkbox.isChecked) {
            Toast.makeText(context, R.string.must_agree_data_collection, Toast.LENGTH_LONG).show()
            return false
        }

        return true
    }
}