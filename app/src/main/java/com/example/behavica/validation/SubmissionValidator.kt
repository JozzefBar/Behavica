package com.example.behavica.validation

import android.widget.CheckBox
import android.widget.Toast
import com.google.android.material.textfield.TextInputEditText

class SubmissionValidator{
    fun validateSubmission(
        dragCompleted: Boolean,
        textInput: TextInputEditText,
        targetText: String,
        checkbox: CheckBox
    ):Boolean{

        if(!dragCompleted) {
            Toast.makeText(checkbox.context, "Please complete the drag test", Toast.LENGTH_LONG).show()
            return false
        }

        val enteredText = textInput.text.toString().trim()
        if(enteredText != targetText){
            Toast.makeText(checkbox.context, "Please rewrite the text correctly", Toast.LENGTH_LONG).show()
            return false
        }

        if (!checkbox.isChecked) {
            Toast.makeText(checkbox.context, "You must agree to data collection", Toast.LENGTH_LONG).show()
            return false
        }

        return true
    }
}