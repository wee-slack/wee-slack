#!/bin/sh -eu

alias curl_slack="curl -H 'Authorization: Bearer $SLACK_TOKEN'"

api_base="https://api.slack.com/api"

if [ ! -d mock_data ]; then
  echo "The mock_data directory must exist" >&2
  exit 1
fi

curl_slack "$api_base/rtm.connect" | jq . > mock_data/slack_rtm_connect.json

curl_slack "$api_base/users.conversations?types=public_channel&exclude_archived=True" | jq . > mock_data/slack_users_conversations_public_channel.json
curl_slack "$api_base/users.conversations?types=private_channel&exclude_archived=True" | jq . > mock_data/slack_users_conversations_private_channel.json
curl_slack "$api_base/users.conversations?types=mpim&exclude_archived=True" | jq . > mock_data/slack_users_conversations_mpim.json
curl_slack "$api_base/users.conversations?types=im&exclude_archived=True" | jq . > mock_data/slack_users_conversations_im.json

curl_slack "$api_base/conversations.info?channel=CK4M8EWJE" | jq . > mock_data/slack_conversations_info_channel_public.json
curl_slack "$api_base/conversations.info?channel=CNZQKUU9M" | jq . > mock_data/slack_conversations_info_channel_private.json
curl_slack "$api_base/conversations.info?channel=GNLENA84B" | jq . > mock_data/slack_conversations_info_channel_group.json
curl_slack "$api_base/conversations.info?channel=C042VL9076F" | jq . > mock_data/slack_conversations_info_mpim_channel.json
curl_slack "$api_base/conversations.info?channel=GKHEJUM1N" | jq . > mock_data/slack_conversations_info_mpim_group.json
curl_slack "$api_base/conversations.info?channel=D9N2KD0V6" | jq . > mock_data/slack_conversations_info_im.json

curl_slack "$api_base/users.info?user=U017V7T2D40" | jq . > mock_data/slack_users_info_person.json
curl_slack "$api_base/users.info?user=UU6635U31" | jq . > mock_data/slack_users_info_bot.json

curl_slack "$api_base/conversations.history?channel=CK4M8EWJE" | jq . > mock_data/slack_conversations_history_channel_public.json
curl_slack "$api_base/conversations.history?channel=D7HHQR467" | jq . > mock_data/slack_conversations_history_im.json

curl_slack "$api_base/usergroups.list?include_users=true" | jq . > mock_data/slack_usergroups_list.json
