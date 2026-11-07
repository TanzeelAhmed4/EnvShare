import re

from rest_framework import serializers

from .encryption import decrypt_value, encrypt_value
from .models import Environment, EnvironmentVariable


MASKED_VALUE = '••••••••'
KEY_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class EnvironmentSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model = Environment
        fields = ('id', 'name', 'label')
        read_only_fields = fields


class EnvironmentVariableSerializer(serializers.ModelSerializer):
    environment_id = serializers.IntegerField(read_only=True)
    value = serializers.CharField(write_only=True, max_length=65536, allow_blank=True)
    sensitivity = serializers.ChoiceField(choices=EnvironmentVariable.Sensitivity.choices)

    class Meta:
        model = EnvironmentVariable
        fields = ('id', 'environment_id', 'key', 'value', 'sensitivity', 'created_at', 'updated_at')
        read_only_fields = ('id', 'environment_id', 'created_at', 'updated_at')

    def validate_key(self, value):
        if not KEY_PATTERN.fullmatch(value):
            raise serializers.ValidationError(
                'Use letters, numbers, and underscores; keys must start with a letter or underscore.'
            )
        environment = self.context['environment']
        duplicates = EnvironmentVariable.objects.filter(environment=environment, key=value)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError('A variable with this key already exists in this environment.')
        return value

    def create(self, validated_data):
        environment = validated_data.pop('environment')
        plaintext = validated_data.pop('value')
        if validated_data['sensitivity'] == EnvironmentVariable.Sensitivity.SENSITIVE:
            stored_value = encrypt_value(plaintext, environment, validated_data['key'])
        else:
            stored_value = plaintext
        return EnvironmentVariable.objects.create(
            environment=environment,
            value=stored_value,
            **validated_data,
        )

    def update(self, instance, validated_data):
        old_key = instance.key
        old_sensitivity = instance.sensitivity
        new_key = validated_data.get('key', old_key)
        new_sensitivity = validated_data.get('sensitivity', old_sensitivity)
        value_supplied = 'value' in validated_data
        plaintext = validated_data.pop('value', None)

        must_decrypt = (
            old_sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
            and not value_supplied
            and (
                new_key != old_key
                or new_sensitivity != old_sensitivity
            )
        )
        if must_decrypt:
            old_plaintext = decrypt_value(instance.value, instance.environment, old_key)
            if not value_supplied:
                plaintext = old_plaintext
        elif not value_supplied and old_sensitivity == EnvironmentVariable.Sensitivity.STANDARD:
            plaintext = instance.value

        instance.key = new_key
        instance.sensitivity = new_sensitivity
        if new_sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE:
            if plaintext is not None:
                instance.value = encrypt_value(plaintext, instance.environment, new_key)
        elif plaintext is not None:
            instance.value = plaintext

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        sensitive = instance.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
        return {
            'id': instance.pk,
            'environment_id': instance.environment_id,
            'key': instance.key,
            'value': MASKED_VALUE if sensitive else instance.value,
            'sensitivity': instance.sensitivity,
            'created_at': self.fields['created_at'].to_representation(instance.created_at),
            'updated_at': self.fields['updated_at'].to_representation(instance.updated_at),
        }
