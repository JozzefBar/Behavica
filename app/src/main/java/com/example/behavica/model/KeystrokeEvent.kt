package com.example.behavica.model

data class KeystrokeEvent(
    val field: String,
    val word: String,
    val type: String,
    val count: Int,
    val timestamp: Long,
    val keyChar: Char,
    val cursorPosition: Int,
    val inputContent: String
) {
    fun toMap(): Map<String, Any> = mapOf(
        "field" to field,
        "word" to word,
        "type" to type,
        "count" to count,
        "timestamp" to timestamp,
        "keyChar" to keyChar.toString(),
        "cursorPosition" to cursorPosition,
        "inputContent" to inputContent
    )
}
