require 'spec_helper'
require_relative '../wee_slack.rb'

module Weechat
  extend self

  def print(arg1, arg2)
    # sends msg to current buffer
    return true
  end
end

describe SlackCommands do
  describe "#debug" do
    it "should print out a test message" do
      expect(Weechat).to receive(:print)
      subject.debug("test")
    end
  end

  describe "#slack" do
    context "with a valid command" do
      it "should call the command" do
        expect(subject).to receive(:help)
        subject.slack("", "", "help")
      end

      context "with additional arguments" do
        it "should pass the arguments to the command" do
          expect(subject).to receive(:help).with(["foo"])
          subject.slack("", "", "help foo")
        end
      end
    end

    context "with an invalid command" do
      it "should print an error" do
        expect(Weechat).to receive(:print)
        subject.slack("", "", "unknown")
      end
    end
  end

  describe "#help" do
    it "should print the available commands to the buffer" do
      expect(Weechat).to receive(:print) do |arg1, arg2|
        expect(arg2).to match(/commands/)
      end
      subject.slack("", "", "help")
    end
  end
end
